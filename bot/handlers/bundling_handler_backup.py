"""
Bundling Handler Orchestrator

This module serves as the main orchestrator for the PumpFun token bundling workflow.
It imports specialized handlers and assembles them into a complete conversation flow.

Architecture:
- wallet_handler: Manages airdrop/bundled wallet creation, funding, and balance checks
- token_config_handler: Handles token parameter input and configuration
- token_creation_handler: Manages final token creation and execution
- bundling_handler: Orchestrates the complete workflow via ConversationHandler
"""

# Core framework imports
from typing import Dict, List, Any, Optional
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext
from loguru import logger

# Bot configuration and utilities
from bot.config import ConversationState, CallbackPrefix
from bot.utils.keyboard_utils import build_button, build_keyboard
from bot.utils.validation_utils import validate_buy_amount, log_validation_result
from bot.utils.message_utils import (
    format_token_parameter_request,
    format_buy_amount_request, 
    format_buy_amounts_preview,
    format_pumpfun_error_message,
    format_wallet_funding_required_message,
    format_wallet_funding_progress_message,
    format_wallet_funding_complete_message,
    format_return_funds_confirmation_message,
    format_return_funds_progress_message,
    format_return_funds_results_message,
    format_return_funds_option_message
)
from bot.state.session_manager import session_manager
from bot.utils.wallet_storage import airdrop_wallet_storage, bundled_wallet_storage

# Specialized handler imports
from .wallet_handler import (
    create_airdrop_wallet, 
    wait_and_retry_airdrop, 
    import_airdrop_wallet, 
    process_airdrop_wallet_import, 
    continue_to_bundled_wallets_setup, 
    bundled_wallets_count
)
from .token_config_handler import (
    token_parameter_input, 
    process_token_image_upload, 
    skip_image_upload, 
    proceed_to_preview, 
    edit_token_parameters
)
from .token_creation_handler import (
    back_to_token_preview, 
    create_token_final,
    is_base58_private_key,
    convert_base64_to_base58
)


def get_user(update: Update, context: CallbackContext):
    """Helper function to get user from update object."""
    if update.callback_query:
        return update.callback_query.from_user
    elif update.message:
        return update.message.from_user
    else:
        return None


def get_query(update: Update):
    """Helper function to get query from update object."""
    return update.callback_query if update.callback_query else None


async def token_creation_start(update: Update, context: CallbackContext) -> int:
    """
    Start the token creation parameter collection process.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Initialize token parameters collection
    session_manager.update_session_value(user.id, "current_token_parameter", "name")
    session_manager.update_session_value(user.id, "token_params", {})
    
    # Request first parameter (token name)
    keyboard = InlineKeyboardMarkup([
        [build_button("« Back to Activities", "back_to_activities")]
    ])
    
    await query.edit_message_text(
        format_token_parameter_request("name", "the name of your token (e.g., 'MyAwesomeToken')"),
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.TOKEN_PARAMETER_INPUT











async def configure_buy_amounts(update: Update, context: CallbackContext) -> int:
    """
    Start buy amounts configuration process after token preview.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Get total bundled wallets count from session
    bundled_wallets_count = session_manager.get_session_value(user.id, "bundled_wallets_count", 0)
    
    # Initialize buy amounts configuration for wallet groups
    wallet_groups = ["DevWallet"]
    
    if bundled_wallets_count > 0:
        # Add first bundled wallets group (up to 4 wallets, minimum 1)
        first_bundled_count = min(4, bundled_wallets_count)
        wallet_groups.append("First Bundled Wallets")
        
        # Add additional child wallets group if more than 4 bundled wallets
        if bundled_wallets_count > 4:
            wallet_groups.append("Additional Child Wallets")
    
    # Store wallet groups configuration
    session_manager.update_session_value(user.id, "buy_amounts_wallet_groups", wallet_groups)
    session_manager.update_session_value(user.id, "current_buy_group_index", 0)
    session_manager.update_session_value(user.id, "buy_amounts", {})
    
    # Store wallet counts for each group
    wallet_group_counts = {
        "DevWallet": 1,
        "First Bundled Wallets": min(4, bundled_wallets_count),
        "Additional Child Wallets": max(0, bundled_wallets_count - 4)
    }
    session_manager.update_session_value(user.id, "wallet_group_counts", wallet_group_counts)
    
    # Show the buy amounts configuration intro
    keyboard = InlineKeyboardMarkup([
        [build_button("Start Configuration", "start_buy_amounts_input")],
        [build_button("« Back to Token Preview", "back_to_token_preview")]
    ])
    
    token_params = session_manager.get_session_value(user.id, "token_params")
    token_name = token_params.get("name", "your token") if token_params else "your token"
    
    await query.edit_message_text(
        f"💰 **Configure Buy Amounts**\n\n"
        f"Now let's configure how much SOL each wallet group should spend to buy **{token_name}** during token creation.\n\n"
        f"**Wallet Groups:**\n"
        f"• **DevWallet** (1 wallet) - Main development wallet\n"
        f"• **First Bundled Wallets** ({min(4, bundled_wallets_count)} wallets) - Primary trading wallets\n" +
        (f"• **Additional Child Wallets** ({max(0, bundled_wallets_count - 4)} wallets) - Extra trading wallets\n" if bundled_wallets_count > 4 else "") +
        f"\n💡 **Important:** Configure these amounts before we check your airdrop wallet balance and fund the bundled wallets.",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.BUY_AMOUNTS_CONFIG


async def start_buy_amounts_input(update: Update, context: CallbackContext) -> int:
    """
    Start the actual buy amounts input process for wallet groups.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Get wallet groups from session
    wallet_groups = session_manager.get_session_value(user.id, "buy_amounts_wallet_groups")
    
    if not wallet_groups:
        # Initialize default groups if not in session
        bundled_wallets_count = session_manager.get_session_value(user.id, "bundled_wallets_count", 0)
        wallet_groups = ["DevWallet"]
        
        if bundled_wallets_count > 0:
            wallet_groups.append("First Bundled Wallets")
            if bundled_wallets_count > 4:
                wallet_groups.append("Additional Child Wallets")
        
        session_manager.update_session_value(user.id, "buy_amounts_wallet_groups", wallet_groups)
        
        # Store wallet counts for each group
        wallet_group_counts = {
            "DevWallet": 1,
            "First Bundled Wallets": min(4, bundled_wallets_count),
            "Additional Child Wallets": max(0, bundled_wallets_count - 4)
        }
        session_manager.update_session_value(user.id, "wallet_group_counts", wallet_group_counts)
    
    # Reset to first wallet group
    session_manager.update_session_value(user.id, "current_buy_group_index", 0)
    
    # Get group description for better context
    group_descriptions = {
        "DevWallet": "Main development wallet",
        "First Bundled Wallets": "Primary trading wallets",
        "Additional Child Wallets": "Extra trading wallets (remaining bundled wallets)"
    }
    
    # Request first wallet group buy amount
    keyboard = InlineKeyboardMarkup([
        [build_button("« Back to Activities", "back_to_activities")]
    ])
    
    await query.edit_message_text(
        format_buy_amount_request(
            wallet_groups[0], 
            1, 
            len(wallet_groups),
            group_descriptions.get(wallet_groups[0], "")
        ),
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.BUY_AMOUNTS_INPUT


async def buy_amounts_input(update: Update, context: CallbackContext) -> int:
    """
    Handle buy amount input from user for wallet groups.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.message.from_user
    amount_input = update.message.text.strip()
    
    # Get current configuration
    wallet_groups = session_manager.get_session_value(user.id, "buy_amounts_wallet_groups")
    current_index = session_manager.get_session_value(user.id, "current_buy_group_index")
    buy_amounts = session_manager.get_session_value(user.id, "buy_amounts") or {}
    wallet_group_counts = session_manager.get_session_value(user.id, "wallet_group_counts") or {}
    
    if not wallet_groups or current_index is None:
        await update.message.reply_text(
            "❌ Configuration error. Please restart the process.",
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.ACTIVITY_SELECTION
    
    current_group = wallet_groups[current_index]
    
    # Validate buy amount
    is_valid, amount_or_error = validate_buy_amount(amount_input)
    log_validation_result(f"buy_amount_{current_group}", amount_input, is_valid, 
                         "" if is_valid else amount_or_error, user.id)
    
    if not is_valid:
        keyboard = InlineKeyboardMarkup([
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await update.message.reply_text(
            f"❌ **Invalid Buy Amount**\n\n{amount_or_error}\n\n"
            f"Please try again:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.BUY_AMOUNTS_INPUT
    
    # Store validated amount for the wallet group
    buy_amounts[current_group] = amount_or_error
    session_manager.update_session_value(user.id, "buy_amounts", buy_amounts)
    
    # Check if we need to ask for more wallet groups
    if current_index + 1 < len(wallet_groups):
        # Move to next wallet group
        next_index = current_index + 1
        session_manager.update_session_value(user.id, "current_buy_group_index", next_index)
        next_group = wallet_groups[next_index]
        
        # Get group description for better context
        group_descriptions = {
            "DevWallet": "Main development wallet",
            "First Bundled Wallets": "Primary trading wallets",
            "Additional Child Wallets": "Extra trading wallets (remaining bundled wallets)"
        }
        
        keyboard = InlineKeyboardMarkup([
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await update.message.reply_text(
            format_buy_amount_request(
                next_group, 
                next_index + 1, 
                len(wallet_groups),
                group_descriptions.get(next_group, "")
            ),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUY_AMOUNTS_INPUT
    else:
        # All amounts collected, show preview
        keyboard = InlineKeyboardMarkup([
            [build_button("💰 Check Wallet Balance", "check_wallet_balance")],
            [build_button("✏️ Edit Amounts", "edit_buy_amounts")],
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await update.message.reply_text(
            format_buy_amounts_preview(buy_amounts, "Token will be created after funding", wallet_group_counts),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUY_AMOUNTS_PREVIEW


async def edit_buy_amounts(update: Update, context: CallbackContext) -> int:
    """
    Allow user to edit buy amounts by restarting the configuration.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Reset buy amounts configuration
    return await configure_buy_amounts(update, context)


async def check_wallet_balance(update: Update, context: CallbackContext) -> int:
    """
    Check wallet balances with corrected flow: bundled wallets first, then airdrop wallet.
    Now uses proper API minimum balance requirements.
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Get session data
    pumpfun_client = session_manager.get_session_value(user.id, "pumpfun_client")
    bundled_wallets_count = session_manager.get_session_value(user.id, "bundled_wallets_count")
    buy_amounts = session_manager.get_session_value(user.id, "buy_amounts")
    
    if not all([pumpfun_client, bundled_wallets_count, buy_amounts]):
        await query.edit_message_text(
            "❌ Session data missing. Please start over.",
            reply_markup=InlineKeyboardMarkup([[build_button("« Back to Activities", "back_to_activities")]])
        )
        return ConversationState.ACTIVITY_SELECTION
    
    # Calculate individual buy amounts per wallet
    dev_wallet_buy_amount = buy_amounts.get("DevWallet", 0.01)
    first_bundled_buy_amount = buy_amounts.get("First Bundled Wallets", 0.01)
    
    # Calculate required balances per API documentation:
    # - DevWallet (tipper): 0.055 SOL minimum + buy amount
    # - Other wallets: 0.025 SOL minimum + buy amount
    dev_wallet_required = 0.055 + dev_wallet_buy_amount
    bundled_wallet_required = 0.025 + first_bundled_buy_amount
    
    await query.edit_message_text("🔍 **Checking Bundled Wallet Balances**...", parse_mode=ParseMode.MARKDOWN)
    
    # STEP 1: Check bundled wallets first
    try:
        # Get airdrop wallet address to load user-specific bundled wallets
        airdrop_wallet_address = session_manager.get_session_value(user.id, "airdrop_wallet_address")
        if not airdrop_wallet_address:
            raise Exception("Airdrop wallet address not found in session")
        
        # Load bundled wallet data for this specific user and airdrop wallet
        bundled_wallets_data = bundled_wallet_storage.load_bundled_wallets(airdrop_wallet_address, user.id)
        
        if not bundled_wallets_data:
            raise Exception(f"No bundled wallets found for user {user.id} with airdrop wallet {airdrop_wallet_address[:8]}...")
        
        funded_count = 0
        total_wallets = len(bundled_wallets_data)
        insufficient_wallets = []
        
        logger.info(f"Checking SOL balance for {total_wallets} bundled wallets with API requirements")
        
        # Check each wallet's SOL balance with proper requirements
        for wallet in bundled_wallets_data:
            # Use normalized address field (bundled_wallet_storage returns normalized structure)
            wallet_address = wallet.get("address") or wallet.get("publicKey")
            wallet_name = wallet.get("name", "Unknown")
            
            if not wallet_address:
                continue
                
            try:
                # Use enhanced SOL balance endpoint
                balance_response = pumpfun_client.get_wallet_sol_balance(wallet_address)
                
                # Extract SOL balance from enhanced response format
                sol_balance = 0
                if "data" in balance_response and "sol" in balance_response["data"]:
                    sol_balance = balance_response["data"]["sol"].get("balance", 0)
                elif "data" in balance_response:
                    # Fallback for legacy format
                    sol_balance = balance_response["data"].get("balance", 0)
                
                # Determine required balance based on wallet role
                if wallet_name == "DevWallet":
                    required_balance = dev_wallet_required
                    logger.info(f"Wallet {wallet_name} ({wallet_address[:8]}...): {sol_balance:.6f} SOL (DevWallet requires {required_balance:.6f} SOL)")
                else:
                    required_balance = bundled_wallet_required
                    logger.info(f"Wallet {wallet_name} ({wallet_address[:8]}...): {sol_balance:.6f} SOL (Bundled wallet requires {required_balance:.6f} SOL)")
                
                if sol_balance >= required_balance:
                    funded_count += 1
                else:
                    insufficient_wallets.append({
                        "name": wallet_name,
                        "address": wallet_address[:8] + "...",
                        "current": sol_balance,
                        "required": required_balance,
                        "shortfall": required_balance - sol_balance
                    })
                    
            except Exception as e:
                logger.error(f"Error checking balance for wallet {wallet_name}: {e}")
                insufficient_wallets.append({
                    "name": wallet_name,
                    "address": wallet_address[:8] + "..." if wallet_address else "Unknown",
                    "current": 0,
                    "required": bundled_wallet_required,
                    "shortfall": bundled_wallet_required,
                    "error": str(e)
                })
        
        all_funded = funded_count == total_wallets
        
        logger.info(f"Bundled wallet funding status: {funded_count}/{total_wallets} wallets funded")
        
        if all_funded:
            # All bundled wallets have sufficient funds
            await context.bot.send_message(
                chat_id=user.id,
                text=f"✅ **All Bundled Wallets Ready**\n\n"
                     f"All {total_wallets} bundled wallets have sufficient SOL.\n\n"
                     f"• DevWallet: {dev_wallet_required:.4f} SOL required\n"
                     f"• Bundled wallets: {bundled_wallet_required:.4f} SOL each required\n\n"
                     f"Ready to proceed with token creation!",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [build_button("🚀 Create Token", "create_token_final")],
                    [build_button("💰 Return Funds First", "return_funds_confirmation")],
                    [build_button("📝 Edit Buy Amounts", "edit_buy_amounts")]
                ])
            )
            return ConversationState.WALLET_FUNDING_PROGRESS
        
        # Some bundled wallets need funding - calculate total needed
        total_funding_needed = sum(wallet["shortfall"] for wallet in insufficient_wallets)
        
        # Create detailed funding message
        funding_details = f"⚠️ **Bundled Wallets Need Funding**\n\n"
        funding_details += f"Ready wallets: {funded_count}/{total_wallets}\n"
        funding_details += f"Total funding needed: {total_funding_needed:.4f} SOL\n\n"
        funding_details += "**Insufficient wallets:**\n"
        
        for wallet in insufficient_wallets[:5]:  # Show first 5 to avoid message length issues
            funding_details += f"• {wallet['name']}: {wallet['current']:.4f} SOL (need {wallet['required']:.4f})\n"
        
        if len(insufficient_wallets) > 5:
            funding_details += f"• ... and {len(insufficient_wallets) - 5} more wallets\n"
            
        funding_details += f"\nChecking airdrop wallet balance..."
        
        await context.bot.send_message(
            chat_id=user.id,
            text=funding_details,
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logger.error(f"Error checking bundled wallets: {e}")
        await context.bot.send_message(
            chat_id=user.id,
            text=f"❌ **Error Checking Bundled Wallets**\n\n"
                 f"Could not check bundled wallet balances: {str(e)}\n\n"
                 f"Proceeding to check airdrop wallet...",
            parse_mode=ParseMode.MARKDOWN
        )
        # Estimate total funding needed based on wallet count and requirements
        total_funding_needed = (dev_wallet_required + (bundled_wallets_count - 1) * bundled_wallet_required)
    
    # STEP 2: Check airdrop wallet balance
    try:
        airdrop_wallet_address = session_manager.get_session_value(user.id, "airdrop_wallet_address")
        if not airdrop_wallet_address:
            raise Exception("Airdrop wallet address not found in session")
        
        balance_response = pumpfun_client.get_wallet_balance(airdrop_wallet_address)
        current_balance = balance_response.get("data", {}).get("balance", 0)
        
        # Add buffer for transaction fees (0.01 SOL for transfers)
        total_needed_with_buffer = total_funding_needed + 0.01
        
        if current_balance >= total_needed_with_buffer:
            # Airdrop wallet has sufficient funds
            await context.bot.send_message(
                chat_id=user.id,
                text=f"✅ **Airdrop Wallet Ready**\n\n"
                     f"Balance: {current_balance:.4f} SOL\n"
                     f"Needed: {total_needed_with_buffer:.4f} SOL\n\n"
                     f"Ready to fund bundled wallets!",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [build_button("💰 Fund Bundled Wallets", "fund_bundled_wallets_now")],
                    [build_button("🔄 Return Funds First", "return_funds_confirmation")],
                    [build_button("🔄 Recheck Balances", "check_wallet_balance")]
                ])
            )
            return ConversationState.WALLET_BALANCE_CHECK
        else:
            # Airdrop wallet needs funding
            shortfall = total_needed_with_buffer - current_balance
            await context.bot.send_message(
                chat_id=user.id,
                text=f"⚠️ **Airdrop Wallet Needs Funding**\n\n"
                     f"Current balance: {current_balance:.4f} SOL\n"
                     f"Required: {total_needed_with_buffer:.4f} SOL\n"
                     f"Shortfall: {shortfall:.4f} SOL\n\n"
                     f"**API Requirements:**\n"
                     f"• DevWallet needs: {dev_wallet_required:.4f} SOL\n"
                     f"• Bundled wallets need: {bundled_wallet_required:.4f} SOL each\n\n"
                     f"**Options:**\n"
                     f"• Fund airdrop wallet with at least {shortfall:.4f} SOL\n"
                     f"• Return funds from bundled wallets to increase airdrop wallet balance\n"
                     f"• Reduce buy amounts to lower funding requirements",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [build_button("💰 Return Funds First", "return_funds_confirmation")],
                    [build_button("🔄 Check Again", "check_wallet_balance")],
                    [build_button("📝 Edit Buy Amounts", "edit_buy_amounts")]
                ])
            )
            return ConversationState.WALLET_FUNDING_REQUIRED
            
    except Exception as e:
        logger.error(f"Error checking airdrop wallet balance: {e}")
        await context.bot.send_message(
            chat_id=user.id,
            text=f"❌ **Error Checking Airdrop Wallet**\n\n"
                 f"Could not check airdrop wallet balance: {str(e)}\n\n"
                 f"Please try again or check your wallet manually.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [build_button("🔄 Try Again", "check_wallet_balance")],
                [build_button("📝 Edit Buy Amounts", "edit_buy_amounts")]
            ])
        )
        return ConversationState.WALLET_BALANCE_CHECK


async def return_funds_confirmation(update: Update, context: CallbackContext) -> int:
    """
    Show confirmation dialog for returning funds to mother wallet.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    try:
        # Get wallet counts for confirmation display
        bundled_wallets_count = session_manager.get_session_value(user.id, "bundled_wallets_count", 0)
        
        # Calculate wallet counts by type
        wallet_counts = {
            "DevWallet": 1,
            "Bundled Wallets": bundled_wallets_count
        }
        
        # Import message formatter
        from bot.utils.message_utils import format_return_funds_confirmation_message
        
        # Show confirmation dialog
        keyboard = InlineKeyboardMarkup([
            [build_button("✅ Yes, Return Funds", "execute_return_funds")],
            [build_button("❌ No, Keep Funds", "check_wallet_balance")],
            [build_button("📝 Edit Buy Amounts", "edit_buy_amounts")]
        ])
        
        await query.edit_message_text(
            format_return_funds_confirmation_message(wallet_counts),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.RETURN_FUNDS_CONFIRMATION
        
    except Exception as e:
        logger.error(
            f"Failed to show return funds confirmation for user {user.id}: {str(e)}",
            extra={"user_id": user.id}
        )
        
        keyboard = InlineKeyboardMarkup([
            [build_button("« Back to Balance Check", "check_wallet_balance")]
        ])
        
        await query.edit_message_text(
            format_pumpfun_error_message("return_funds_confirmation", str(e)),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_BALANCE_CHECK


async def execute_return_funds(update: Update, context: CallbackContext) -> int:
    """
    Execute the return funds operation.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    try:
        # Get required data from session
        pumpfun_client = session_manager.get_session_value(user.id, "pumpfun_client")
        bundled_wallets_count = session_manager.get_session_value(user.id, "bundled_wallets_count", 0)
        airdrop_wallet_address = session_manager.get_session_value(user.id, "airdrop_wallet_address")
        
        if not pumpfun_client:
            raise Exception("PumpFun client not found in session")
        if not airdrop_wallet_address:
            raise Exception("Airdrop wallet address not found in session")
        
        # Import message formatter
        from bot.utils.message_utils import format_return_funds_progress_message
        
        # Show initial progress message
        await query.edit_message_text(
            format_return_funds_progress_message({
                "processed": 0,
                "total": bundled_wallets_count + 1,  # +1 for DevWallet
                "successful": 0,
                "failed": 0,
                "current_operation": "Initiating return funds operation..."
            }),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # UPDATED: Use new stateless API format - no need for pre-importing wallets
        logger.info(f"Starting return funds operation for user {user.id} with new API format")
        
        # Show initial progress message
        await query.edit_message_text(
            format_return_funds_progress_message({
                "processed": 0,
                "total": bundled_wallets_count,
                "successful": 0,
                "failed": 0,
                "current_operation": "Preparing return funds operation..."
            }),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Store prepared child wallets for new API format
        child_wallets_credentials = []
        
        # Get bundled wallets credentials from session or storage
        bundled_wallets_original_json = session_manager.get_session_value(user.id, "bundled_wallets_original_json")
        if not bundled_wallets_original_json:
            bundled_wallets_data = session_manager.get_session_value(user.id, "bundled_wallets_data")
            if bundled_wallets_data:
                bundled_wallets_original_json = {"data": bundled_wallets_data}
        
        # Load from storage if not in session
        if not bundled_wallets_original_json:
            bundled_wallets_original_json = bundled_wallet_storage.load_bundled_wallets(airdrop_wallet_address, user.id)
            
        if isinstance(bundled_wallets_original_json, list):
            wallets_to_process = bundled_wallets_original_json
        elif isinstance(bundled_wallets_original_json, dict) and "data" in bundled_wallets_original_json:
            wallets_to_process = bundled_wallets_original_json["data"]
        elif isinstance(bundled_wallets_original_json, dict) and "wallets" in bundled_wallets_original_json:
            wallets_to_process = bundled_wallets_original_json["wallets"]
        else:
            wallets_to_process = []
            
        child_wallets_credentials = []
        for wallet in wallets_to_process:
            if isinstance(wallet, dict):
                private_key = wallet.get("privateKey") or wallet.get("private_key") or wallet.get("privateKeyBs58")
                name = wallet.get("name", "Unknown")
                
                if private_key and name:
                    # Convert to base58 format if needed
                    if is_base58_private_key(private_key):
                        private_key_bs58 = private_key
                    else:
                        private_key_bs58 = convert_base64_to_base58(private_key)
                    
                    child_wallets_credentials.append({
                        "name": name,
                        "privateKey": private_key_bs58
                    })
        
        if not child_wallets_credentials:
            raise Exception("No child wallet credentials found for return funds operation")

        # Execute return funds operation with new API format
        logger.info(f"Executing return funds operation with {len(child_wallets_credentials)} child wallets")
        
        # Show operation progress
        await query.edit_message_text(
            format_return_funds_progress_message({
                "processed": 0,
                "total": len(child_wallets_credentials),
                "successful": 0,
                "failed": 0,
                "current_operation": "Executing return funds operation..."
            }),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return_results = pumpfun_client.return_funds_to_mother(
            mother_wallet_public_key=airdrop_wallet_address,
            child_wallets=child_wallets_credentials
        )
        
        # Enhanced response validation and logging
        logger.info(f"Return funds API response for user {user.id}: {json.dumps(return_results, default=str, indent=2)}")
        
        # Validate response structure
        if not return_results:
            logger.error(f"Empty response from return funds API for user {user.id}")
            return_results = {
                "message": "Return funds operation completed but response was empty",
                "data": {
                    "totalWallets": bundled_wallets_count,
                    "successfulTransfers": 0,
                    "failedTransfers": 0,
                    "totalAmount": 0
                }
            }
        elif isinstance(return_results, list):
            logger.warning(f"Return funds API returned a list instead of dictionary for user {user.id}")
            # Convert list response to expected dictionary format
            list_results = return_results
            return_results = {
                "message": "Return funds operation completed",
                "data": {
                    "totalWallets": len(list_results),
                    "successfulTransfers": len([r for r in list_results if r.get('status') == 'success']),
                    "failedTransfers": len([r for r in list_results if r.get('status') == 'failed']),
                    "totalAmount": sum(r.get('amount', 0) for r in list_results if r.get('status') == 'success'),
                    "transactions": list_results
                }
            }
        elif not isinstance(return_results, dict):
            logger.error(f"Unexpected response type from return funds API for user {user.id}: {type(return_results)}")
            return_results = {
                "message": "Return funds operation completed but response format was unexpected",
                "data": {
                    "totalWallets": bundled_wallets_count,
                    "successfulTransfers": 0,
                    "failedTransfers": 0,
                    "totalAmount": 0,
                    "error": f"Unexpected response type: {type(return_results)}"
                }
            }
        
        # Store results in session
        session_manager.update_session_value(user.id, "return_funds_results", return_results)
        
        # Enhanced logging for debugging per API documentation
        logger.info(f"Return funds operation completed for user {user.id}")
        if "data" in return_results:
            data = return_results["data"]
            logger.info(f"  Enhanced return funds results:")
            logger.info(f"    Total wallets processed: {data.get('totalWallets', 'N/A')}")
            logger.info(f"    Successful transfers: {data.get('successfulTransfers', 'N/A')}")
            logger.info(f"    Failed transfers: {data.get('failedTransfers', 'N/A')}")
            logger.info(f"    Total amount returned: {data.get('totalAmount', 'N/A')} SOL")
            logger.info(f"    Fee calculation applied: {data.get('feeCalculation', 'N/A')}")
            logger.info(f"    Bundle ID: {data.get('bundleId', 'N/A')}")
        
        # Show completion message
        keyboard = InlineKeyboardMarkup([
            [build_button("🔄 Check Balance Again", "check_wallet_balance")],
            [build_button("🚀 Proceed to Token Creation", "create_token_final")]
        ])
        
        # Import message formatter
        from bot.utils.message_utils import format_return_funds_results_message
        
        # Try to format the message with enhanced error handling
        try:
            formatted_message = format_return_funds_results_message(return_results)
        except Exception as format_error:
            logger.error(f"Error formatting return funds results message for user {user.id}: {str(format_error)}")
            # Fallback message
            formatted_message = (
                f"✅ **Funds Return Complete**\n\n"
                f"The return funds operation has been completed. Please check your wallet balances.\n\n"
                f"**Note:** There was an issue formatting the detailed results, but the operation should have succeeded.\n\n"
                f"🎉 **Your airdrop wallet should now be ready for fresh funding!**"
            )
        
        await query.edit_message_text(
            formatted_message,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.RETURN_FUNDS_COMPLETE
        
    except Exception as e:
        error_message = str(e).lower()
        
        # Enhanced error detection for insufficient funds scenarios per API documentation
        insufficient_funds_patterns = [
            "custom program error: 1",     # Primary insufficient lamports error
            "insufficient funds",          # Standard insufficient funds
            "insufficient lamports",       # Lamports-specific error
            "insufficient balance",        # Balance-specific error
            "not enough sol",             # Alternative phrasing
            "insufficient account balance", # Account balance error
            "each wallet needs at least",  # Our enhanced error message
            "insufficient funds for rent", # Rent exemption error
            "program error: \"insufficient funds for rent", # Specific rent error format
            "insufficient funds for rent:", # Rent error with colon
        ]
        
        is_insufficient_funds = any(pattern in error_message for pattern in insufficient_funds_patterns)
        
        if is_insufficient_funds:
            logger.error(f"Enhanced insufficient funds error detected for user {user.id}")
            logger.error(f"  Error details: {str(e)}")
            logger.error(f"  Airdrop wallet: {airdrop_wallet_address}")
            logger.error(f"  Bundled wallets count: {bundled_wallets_count}")
            logger.error(f"  Recommendation: Check individual wallet balances and ensure minimum reserve + fee requirements are met")
            
            # Check if this is a rent-related error
            error_message_lower = str(e).lower()
            is_rent_error = any(pattern in error_message_lower for pattern in [
                "insufficient funds for rent", 
                "program error: \"insufficient funds for rent"
            ])
            
            # Show enhanced insufficient funds error message
            keyboard = InlineKeyboardMarkup([
                [build_button("📊 Check Individual Balances", "check_wallet_balance")],
                [build_button("💰 Fund Wallets First", "fund_bundled_wallets_now")],
                [build_button("🔄 Try Again", "execute_return_funds")]
            ])
            
            if is_rent_error:
                insufficient_funds_message = (
                    "⚠️ **Insufficient Funds for Rent Exemption**\n\n"
                    "The return funds operation failed because one or more wallets don't have enough SOL for rent exemption.\n\n"
                    "**Rent Error Details:**\n"
                    f"• {str(e)}\n\n"
                    "**Per API Documentation Requirements:**\n"
                    "• Rent exemption (ATA): 0.00203928 SOL per wallet\n"
                    "• Transaction fees: 0.000025 SOL per transaction\n"
                    "• Wallet management reserve: 0.0001 SOL per wallet\n"
                    "• **TOTAL minimum per wallet: ~0.00216 SOL**\n\n"
                    "**Recommended Actions:**\n"
                    "1. Fund each wallet with at least 0.0025 SOL for safety margin\n"
                    "2. Check individual wallet balances\n"
                    "3. Some wallets may have been emptied below rent exemption\n"
                    "4. Fund the affected wallets before retrying\n\n"
                    "**Note:** Solana accounts need minimum SOL for rent exemption to remain active."
                )
            else:
                insufficient_funds_message = (
                    "⚠️ **Insufficient Funds for Return Operation**\n\n"
                    "The return funds operation failed due to insufficient balances in one or more wallets.\n\n"
                    "**Enhanced Error Details:**\n"
                    f"• {str(e)}\n\n"
                    "**Per API Documentation Requirements:**\n"
                    "• Rent exemption (ATA): 0.00203928 SOL per wallet\n"
                    "• Transaction fees: 0.000025 SOL per transaction\n"
                    "• Wallet management reserve: 0.0001 SOL per wallet\n"
                    "• Enhanced fee calculation: Base 5,000 + Priority 20,000 lamports\n"
                    "• **TOTAL minimum per wallet: ~0.00216 SOL**\n\n"
                    "**Recommended Actions:**\n"
                    "1. Check individual wallet balances\n"
                    "2. Fund wallets with at least 0.0025 SOL each for safety margin\n"
                    "3. Ensure each wallet meets minimum balance requirements\n"
                    "4. Try the operation again"
                )
            
            await query.edit_message_text(
                insufficient_funds_message,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
        else:
            # Handle other types of errors (non-balance related)
            logger.error(f"Return funds operation failed for user {user.id}: {str(e)}")
            logger.error(f"  Error type: {type(e).__name__}")
            logger.error(f"  Error category: Non-balance error")
            logger.error(f"  Airdrop wallet: {airdrop_wallet_address}")
            logger.error(f"  Bundled wallets count: {bundled_wallets_count}")
            
            # Determine appropriate error handling based on error type
            if "server configuration" in error_message:
                keyboard = InlineKeyboardMarkup([
                    [build_button("📊 Check API Status", "check_api_status")],
                    [build_button("🔄 Wait & Retry", "wait_and_retry_import")],
                    [build_button("« Back to Balance Check", "check_wallet_balance")]
                ])
                
                error_title = "**Server Configuration Error**"
                error_context = "The API server has a configuration issue that prevents the return funds operation."
                
            elif "timeout" in error_message or "connection" in error_message:
                keyboard = InlineKeyboardMarkup([
                    [build_button("🔄 Try Again", "execute_return_funds")],
                    [build_button("⏱️ Wait & Retry", "wait_and_retry_import")],
                    [build_button("« Back to Balance Check", "check_wallet_balance")]
                ])
                
                error_title = "**Connection Error**"
                error_context = "The operation failed due to a network or connection issue."
                
            else:
                keyboard = InlineKeyboardMarkup([
                    [build_button("🔄 Try Again", "execute_return_funds")],
                    [build_button("« Back to Balance Check", "check_wallet_balance")]
                ])
                
                error_title = "**Operation Error**"
                error_context = "The return funds operation encountered an unexpected error."
            
            await query.edit_message_text(
                f"❌ {error_title}\n\n"
                f"{error_context}\n\n"
                f"**Error Details:**\n"
                f"• {str(e)}\n\n"
                f"**Next Steps:**\n"
                f"• Try the operation again\n"
                f"• Check your wallet balances\n"
                f"• Ensure API server is operational\n"
                f"• Contact support if the issue persists",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        
        return ConversationState.RETURN_FUNDS_CONFIRMATION


async def return_funds_complete(update: Update, context: CallbackContext) -> int:
    """
    Handle return funds completion and provide next steps.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    try:
        choice = query.data
        
        if choice == "check_wallet_balance":
            # Re-check wallet balance after return funds
            return await check_wallet_balance(update, context)
        elif choice == "create_token_final":
            # Proceed to token creation
            return await create_token_final(update, context)
        else:
            # Unknown choice, redirect to balance check
            return await check_wallet_balance(update, context)
        
    except Exception as e:
        logger.error(
            f"Return funds completion failed for user {user.id}: {str(e)}",
            extra={"user_id": user.id}
        )
        
        keyboard = InlineKeyboardMarkup([
            [build_button("« Back to Balance Check", "check_wallet_balance")]
        ])
        
        await query.edit_message_text(
            format_pumpfun_error_message("return_funds_completion", str(e)),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_BALANCE_CHECK


async def fund_bundled_wallets_now(update: Update, context: CallbackContext) -> int:
    """
    Fund bundled wallets with SOL from airdrop wallet.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    try:
        # Get required data from session
        pumpfun_client = session_manager.get_session_value(user.id, "pumpfun_client")
        bundled_wallets_count = session_manager.get_session_value(user.id, "bundled_wallets_count")
        airdrop_wallet = session_manager.get_session_value(user.id, "airdrop_wallet_address")
        buy_amounts = session_manager.get_session_value(user.id, "buy_amounts")
        
        if not all([pumpfun_client, bundled_wallets_count, airdrop_wallet]):
            raise Exception("Missing required session data for wallet funding")
        
        # Show funding requirement message
        keyboard = InlineKeyboardMarkup([
            [build_button("💰 Start Funding", "start_wallet_funding")],
            [build_button("« Back to Balance Check", "check_wallet_balance")]
        ])
        
        await query.edit_message_text(
            format_wallet_funding_required_message(airdrop_wallet, bundled_wallets_count, buy_amounts),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_FUNDING_REQUIRED
        
    except Exception as e:
        logger.error(
            f"Failed to show funding requirement for user {user.id}: {str(e)}",
            extra={"user_id": user.id}
        )
        
        keyboard = InlineKeyboardMarkup([
            [build_button("Try Again", "fund_bundled_wallets_now")],
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await query.edit_message_text(
            format_pumpfun_error_message("funding_requirement", str(e)),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_BALANCE_CHECK


async def start_wallet_funding(update: Update, context: CallbackContext) -> int:
    """
    Start the actual wallet funding process.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    try:
        # Get required data from session with validation
        pumpfun_client = session_manager.get_session_value(user.id, "pumpfun_client")
        bundled_wallets_count = session_manager.get_session_value(user.id, "bundled_wallets_count")
        airdrop_wallet = session_manager.get_session_value(user.id, "airdrop_wallet_address")
        bundled_wallets = session_manager.get_session_value(user.id, "bundled_wallets")
        
        # Validate all required data is present
        if not pumpfun_client:
            raise Exception("PumpFun client not found in session - please restart the workflow")
        if not bundled_wallets_count:
            raise Exception("Bundled wallets count not found in session")
        if not airdrop_wallet:
            raise Exception("Airdrop wallet not found in session")
        if not bundled_wallets or len(bundled_wallets) == 0:
            raise Exception("No bundled wallets found - please create bundled wallets first")
        
        # Validate bundled wallets count matches actual wallets
        if len(bundled_wallets) != bundled_wallets_count:
            logger.warning(f"Bundled wallets count mismatch: expected {bundled_wallets_count}, found {len(bundled_wallets)}")
            bundled_wallets_count = len(bundled_wallets)  # Use actual count
            session_manager.update_session_value(user.id, "bundled_wallets_count", bundled_wallets_count)
        
        # Import airdrop wallet to API if available
        airdrop_private_key = session_manager.get_session_value(user.id, "airdrop_private_key")
        if airdrop_private_key:
            try:
                pumpfun_client.create_airdrop_wallet(airdrop_private_key)
                logger.info(f"Successfully imported airdrop wallet to API for user {user.id}")
                
            except Exception as import_error:
                logger.warning(f"Failed to import airdrop wallet to API: {str(import_error)}")
                # Continue with funding - the wallet might already exist on API
        else:
            logger.warning(f"No airdrop private key found for user {user.id}, proceeding without import")
        
        # Ensure bundled wallets are imported to API before funding
        bundled_wallets_data = session_manager.get_session_value(user.id, "bundled_wallets_data")
        bundled_wallets_original_json = session_manager.get_session_value(user.id, "bundled_wallets_original_json")
        
        # DEBUG: Add comprehensive logging for systematic debugging
        logger.info(f"DEBUG: Checking bundled_wallets_data for user {user.id}")
        logger.info(f"DEBUG: bundled_wallets_data type: {type(bundled_wallets_data)}")
        logger.info(f"DEBUG: bundled_wallets_data is None: {bundled_wallets_data is None}")
        logger.info(f"DEBUG: bundled_wallets_original_json type: {type(bundled_wallets_original_json)}")
        logger.info(f"DEBUG: bundled_wallets_original_json is None: {bundled_wallets_original_json is None}")
        
        # Prefer original JSON data for API import (preserves privateKey format)
        data_source = bundled_wallets_original_json if bundled_wallets_original_json else bundled_wallets_data
        data_source_name = "original_json" if bundled_wallets_original_json else "normalized_data"
        
        if data_source:
            logger.info(f"DEBUG: Using {data_source_name} as data source")
            logger.info(f"DEBUG: data_source keys: {list(data_source.keys()) if isinstance(data_source, dict) else 'Not a dict'}")
            logger.info(f"DEBUG: data_source length: {len(data_source) if hasattr(data_source, '__len__') else 'No length'}")
            
            try:
                # Extract wallets from data structure - could be a list or dict with "data" key
                wallets_to_import = []
                
                if isinstance(data_source, list):
                    # Direct list of wallets
                    wallets_to_import = data_source
                    logger.info(f"DEBUG: Using direct list format with {len(wallets_to_import)} wallets")
                elif isinstance(data_source, dict) and "data" in data_source:
                    # JSON file format with "data" array (THIS IS THE EXPECTED FORMAT)
                    wallets_to_import = data_source["data"]
                    logger.info(f"DEBUG: Using dict.data format with {len(wallets_to_import)} wallets")
                elif isinstance(data_source, dict) and "wallets" in data_source:
                    # Alternative format with "wallets" array
                    wallets_to_import = data_source["wallets"]
                    logger.info(f"DEBUG: Using dict.wallets format with {len(wallets_to_import)} wallets")
                else:
                    logger.error(f"DEBUG: Unknown data_source format: {data_source}")
                
                if wallets_to_import and len(wallets_to_import) > 0:
                    logger.info(f"Importing {len(wallets_to_import)} bundled wallets to API for user {user.id}")
                    
                    # DEBUG: Log first wallet structure for analysis
                    first_wallet = wallets_to_import[0] if wallets_to_import else None
                    if first_wallet:
                        logger.info(f"DEBUG: First wallet structure: {first_wallet}")
                        logger.info(f"DEBUG: First wallet keys: {list(first_wallet.keys()) if isinstance(first_wallet, dict) else 'Not a dict'}")
                    
                    # Protected UI update before API import - CRITICAL: Do not let UI errors stop API operations
                    try:
                        await query.edit_message_text(
                            format_wallet_funding_progress_message({
                                "processed": 0,
                                "total": bundled_wallets_count,
                                "successful": 0,
                                "failed": 0,
                                "current_wallet": "Importing bundled wallets to API..."
                            }),
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except Exception as ui_pre_import_error:
                        # UI errors before API import should not stop the process - CRITICAL: Do not re-raise
                        logger.warning(f"UI update before API import failed, continuing with import: {ui_pre_import_error}")
                        # IMPORTANT: Do not raise this error - it would be caught by outer exception handler
                    
                    # Format bundled wallets for API import (name and privateKeyBs58 fields)
                    api_wallets = []
                    for i, wallet in enumerate(wallets_to_import):
                        if isinstance(wallet, dict):
                            # Handle different key formats (privateKey vs private_key vs privateKeyBs58)
                            private_key = wallet.get("privateKey") or wallet.get("private_key") or wallet.get("privateKeyBs58")
                            name = wallet.get("name", f"Wallet_{len(api_wallets) + 1}")
                            
                            logger.info(f"DEBUG: Processing wallet {i}: name='{name}', has_privateKey={bool(wallet.get('privateKey'))}, has_private_key={bool(wallet.get('private_key'))}, has_privateKeyBs58={bool(wallet.get('privateKeyBs58'))}")
                            
                            if private_key:
                                api_wallets.append({
                                    "name": name,
                                    "privateKey": private_key
                                })
                                logger.info(f"DEBUG: Added wallet '{name}' to API import list with validated base58 key")
                            else:
                                logger.warning(f"Bundled wallet missing private key, skipping: {wallet.get('name', 'Unknown')}")
                                logger.warning(f"DEBUG: Wallet {i} keys: {list(wallet.keys())}")
                    
                    logger.info(f"DEBUG: Prepared {len(api_wallets)} wallets for API import")
                    
                    if api_wallets:
                        # DEBUG: Log what we're about to send to API
                        logger.info(f"DEBUG: Sending {len(api_wallets)} wallets to API import")
                        for i, api_wallet in enumerate(api_wallets):
                            private_key_field = api_wallet.get('privateKey') or api_wallet.get('privateKeyBs58')
                            logger.info(f"DEBUG: API wallet {i}: name='{api_wallet['name']}', privateKey_length={len(private_key_field) if private_key_field else 0}")
                        
                        # PHASE 2 FIX: Separate API operation from UI operation
                        api_import_success = False
                        api_import_error = None
                        
                        try:
                            # Import bundled wallets to API (CRITICAL OPERATION)
                            import_result = pumpfun_client.import_bundled_wallets(api_wallets)
                            logger.info(f"Successfully imported {len(api_wallets)} bundled wallets to API for user {user.id}")
                            logger.info(f"DEBUG: Import result: {import_result}")
                            api_import_success = True
                            
                        except Exception as api_import_error:
                            logger.error(f"API import failed: {str(api_import_error)}")
                            logger.error(f"DEBUG: API import error type: {type(api_import_error)}")
                            logger.error(f"DEBUG: API import error details: {repr(api_import_error)}")
                            
                            # Enhanced error recovery for specific server-side issues
                            error_message = str(api_import_error)
                            
                            if "bs58.decode is not a function" in error_message:
                                logger.error("Server-side bs58 library issue detected - this requires server configuration fix")
                                # This is a server configuration issue that cannot be fixed client-side
                                api_import_success = False
                                api_import_error = Exception(
                                    "Server configuration error: bs58 library not properly installed. "
                                    "Contact API administrator to install: npm install bs58"
                                )
                            elif "bs58" in error_message.lower():
                                logger.error("Server-side base58 processing issue detected")
                                # Try a different approach - maybe retry with explicit format
                                api_import_success = False
                                api_import_error = Exception(
                                    f"Server base58 processing error: {error_message}. "
                                    "Private key format validation passed client-side but failed server-side."
                                )
                            else:
                                # Other types of errors - standard handling
                                api_import_success = False
                                api_import_error = api_import_error
                        
                        # Only update UI after API operation completes (success or failure)
                        try:
                            if api_import_success:
                                await query.edit_message_text(
                                    format_wallet_funding_progress_message({
                                        "processed": 0,
                                        "total": bundled_wallets_count,
                                        "successful": 0,
                                        "failed": 0,
                                        "current_wallet": "✅ Bundled wallets imported successfully. Verifying..."
                                    }),
                                    parse_mode=ParseMode.MARKDOWN
                                )
                            else:
                                await query.edit_message_text(
                                    format_wallet_funding_progress_message({
                                        "processed": 0,
                                        "total": bundled_wallets_count,
                                        "successful": 0,
                                        "failed": 0,
                                        "current_wallet": f"⚠️ Import issue detected. Attempting verification..."
                                    }),
                                    parse_mode=ParseMode.MARKDOWN
                                )
                        except Exception as ui_error:
                            # UI errors should not stop the process - CRITICAL: Do not re-raise these
                            logger.warning(f"UI update failed but API operation status: {api_import_success}, continuing: {ui_error}")
                            # IMPORTANT: Do not raise this error - it would be caught by outer exception handler
                        
                        # PHASE 2 FIX: Add verification step
                        verification_result = pumpfun_client.verify_bundled_wallets_exist()
                        wallets_verified = verification_result.get("wallets_exist", False)
                        
                        logger.info(f"Wallet verification result: {verification_result}")
                        
                        if not wallets_verified and not api_import_success:
                            # Both import and verification failed - this is a critical error
                            logger.error(f"CRITICAL: Bundled wallet import failed AND verification failed")
                            
                            # Try a recovery mechanism: attempt import one more time
                            logger.info("Attempting recovery: retrying wallet import once...")
                            
                            try:
                                await query.edit_message_text(
                                    format_wallet_funding_progress_message({
                                        "processed": 0,
                                        "total": bundled_wallets_count,
                                        "successful": 0,
                                        "failed": 0,
                                        "current_wallet": "🔄 Retrying wallet import (recovery attempt)..."
                                    }),
                                    parse_mode=ParseMode.MARKDOWN
                                )
                            except Exception as ui_recovery_error:
                                # Ignore UI errors during recovery - CRITICAL: Do not re-raise
                                logger.warning(f"UI update during recovery failed, continuing: {ui_recovery_error}")
                                # IMPORTANT: Do not raise this error - it would be caught by outer exception handler
                            
                            # Recovery attempt
                            recovery_result = pumpfun_client.import_bundled_wallets(api_wallets)
                            recovery_verification = pumpfun_client.verify_bundled_wallets_exist()
                            
                            if not recovery_verification.get("wallets_exist", False):
                                # Recovery failed - raise error to stop the process
                                error_msg = f"Bundled wallet import failed repeatedly. Original error: {api_import_error}. Recovery also failed."
                                logger.error(error_msg)
                                raise Exception(error_msg)
                            else:
                                logger.info("✅ Recovery successful - wallets imported on second attempt")
                                wallets_verified = True
                        
                        if wallets_verified:
                            logger.info("✅ Bundled wallets are verified on the API server")
                        else:
                            logger.warning("⚠️ Bundled wallets could not be verified on the API server, but import did not throw error. Proceeding with caution.")
                            
                else:
                    logger.warning(f"No bundled wallets to import for user {user.id}")
            
            except Exception as e:
                logger.error(f"Error during bundled wallet import process for user {user.id}: {str(e)}")
                # Do not re-raise - allow funding to proceed if possible
        
        # Get buy amounts from session
        buy_amounts = session_manager.get_session_value(user.id, "buy_amounts")
        if not buy_amounts:
            raise Exception("Buy amounts not configured")
        
        # Calculate funding amounts per wallet
        dev_wallet_buy_amount = buy_amounts.get("DevWallet", 0.01)
        first_bundled_buy_amount = buy_amounts.get("First Bundled Wallets", 0.01)
        
        # Calculate required balances per API documentation
        dev_wallet_required = 0.055 + dev_wallet_buy_amount
        bundled_wallet_required = 0.025 + first_bundled_buy_amount
        
        # Prepare funding data for API
        funding_data = {
            "devWallet": {"amount": dev_wallet_required},
            "firstBundledWallets": {"amount": bundled_wallet_required},
            "additionalChildWallets": {"amount": bundled_wallet_required}
        }
        
        # Execute funding operation
        logger.info(f"Executing wallet funding for user {user.id}")
        
        funding_results = pumpfun_client.fund_bundled_wallets(
            airdrop_wallet_address=airdrop_wallet,
            funding_amounts=funding_data
        )
        
        # Store results in session
        session_manager.update_session_value(user.id, "funding_results", funding_results)
        
        # Show completion message
        keyboard = InlineKeyboardMarkup([
            [build_button("🚀 Create Token", "create_token_final")],
            [build_button("🔄 Recheck Balances", "check_wallet_balance")]
        ])
        
        await query.edit_message_text(
            format_wallet_funding_complete_message(funding_results),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_FUNDING_COMPLETE
        
    except Exception as e:
        logger.error(
            f"Wallet funding failed for user {user.id}: {str(e)}",
            extra={"user_id": user.id},
            exc_info=True
        )
        
        keyboard = InlineKeyboardMarkup([
            [build_button("🔄 Try Again", "start_wallet_funding")],
            [build_button("« Back to Balance Check", "check_wallet_balance")]
        ])
        
        # Analyze error type for better recovery guidance
        error_msg = str(e).lower()
        is_prerequisite_error = any(keyword in error_msg for keyword in 
                                   ["not found", "missing", "airdrop wallet", "bundled wallets"])
        is_validation_error = any(keyword in error_msg for keyword in 
                                 ["insufficient", "balance", "minimum", "funding"])
        
        if is_prerequisite_error:
            keyboard = InlineKeyboardMarkup([
                [build_button("🔄 Restart Setup", "back_to_activities")],
                [build_button("📋 Check Prerequisites", "check_funding_prerequisites")]
            ])
            
            error_message = (
                "❌ **Setup Prerequisites Missing**\n\n"
                f"The wallet funding process failed because some required setup is missing:\n\n"
                f"**Error:** {error_msg}\n\n"
                f"**Next Steps:**\n"
                f"1. Ensure you have created/imported an airdrop wallet\n"
                f"2. Ensure you have created bundled wallets\n"
                f"3. Ensure your airdrop wallet has sufficient SOL balance\n\n"
                f"Click 'Restart Setup' to go through the complete process again."
            )
        elif is_validation_error:
            keyboard = InlineKeyboardMarkup([
                [build_button("🔄 Retry Funding", "start_wallet_funding")],
                [build_button("📊 Check Balance", "check_wallet_balance")],
                [build_button("« Back to Balance Check", "check_wallet_balance")]
            ])
            
            error_message = (
                "❌ **API Validation Error**\n\n"
                f"The funding request was rejected by the API:\n\n"
                f"**Error:** {error_msg}\n\n"
                f"**Possible Causes:**\n"
                f"• API format requirements differ from documentation\n"
                f"• Airdrop wallet not properly configured on API side\n"
                f"• Bundled wallets not properly created on API side\n"
                f"• Insufficient SOL balance in airdrop wallet\n\n"
                f"Click 'Check Balance' to verify your wallet status, or 'Retry Funding' to try again."
            )
        else:
            keyboard = InlineKeyboardMarkup([
                [build_button("Try Again", "start_wallet_funding")],
                [build_button("« Back to Balance Check", "check_wallet_balance")]
            ])
            error_message = format_pumpfun_error_message("wallet_funding", str(e))
        
        await query.edit_message_text(
            error_message,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_FUNDING_REQUIRED


async def retry_wallet_funding(update: Update, context: CallbackContext) -> int:
    """
    Retry funding for failed wallets.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Simply restart the funding process
    return await start_wallet_funding(update, context)


async def use_existing_airdrop_wallet(update: Update, context: CallbackContext) -> int:
    """
    Handle using an existing airdrop wallet.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    try:
        # Get existing wallets for this user
        existing_wallets = airdrop_wallet_storage.list_user_airdrop_wallets(user.id)
        
        if not existing_wallets:
            # No wallets found, redirect to creation
            await query.edit_message_text(
                "❌ **No Existing Airdrop Wallets Found**\n\n"
                "No saved airdrop wallets found for your account. Please create or import one.",
                reply_markup=InlineKeyboardMarkup([
                    [build_button("Create Airdrop Wallet", "create_airdrop_wallet")],
                    [build_button("Import Airdrop Wallet", "import_airdrop_wallet")],
                    [build_button("« Back to Activities", "back_to_activities")]
                ]),
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationState.BUNDLING_WALLET_SETUP
        
        if len(existing_wallets) == 1:
            # Only one wallet, use it directly
            wallet_data = existing_wallets[0]
            wallet_address = wallet_data["wallet_address"]
            
            # Store wallet information in session
            session_manager.update_session_value(user.id, "airdrop_wallet_address", wallet_address)
            # Store private key if available (for created/imported wallets)
            if wallet_data.get("private_key"):
                session_manager.update_session_value(user.id, "airdrop_private_key", wallet_data["private_key"])
            
            logger.info(
                f"Using existing airdrop wallet for user {user.id}",
                extra={"user_id": user.id, "wallet_address": wallet_address}
            )
            
            # Show success message and proceed
            keyboard = InlineKeyboardMarkup([
                [build_button("Continue", "continue_to_bundled_count")]
            ])
            
            created_date = wallet_data.get("created_at", "Unknown")
            wallet_type = "Imported" if wallet_data.get("imported") else "Created"
            
            await query.edit_message_text(
                f"✅ **Using Existing Airdrop Wallet**\n\n"
                f"**Address:** `{wallet_address}`\n"
                f"**Type:** {wallet_type}\n"
                f"**Created:** {created_date[:10] if created_date != 'Unknown' else created_date}\n\n"
                f"Ready to proceed with bundled wallet creation.",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.BUNDLED_WALLETS_COUNT
        
        else:
            # Multiple wallets, let user choose
            keyboard = []
            for i, wallet_data in enumerate(existing_wallets[:5]):  # Limit to 5 for UI
                wallet_address = wallet_data["wallet_address"]
                created_date = wallet_data.get("created_at", "Unknown")
                wallet_type = "Imported" if wallet_data.get("imported") else "Created"
                
                short_address = f"{wallet_address[:8]}...{wallet_address[-8:]}"
                button_text = f"{wallet_type}: {short_address}"
                
                keyboard.append([build_button(button_text, f"select_airdrop_{i}")])
            
            keyboard.append([build_button("« Back to Setup", "back_to_bundling_setup")])
            
            # Store wallets in session for selection
            session_manager.update_session_value(user.id, "available_airdrop_wallets", existing_wallets[:5])
            
            await query.edit_message_text(
                f"📋 **Select Airdrop Wallet**\n\n"
                f"Found {len(existing_wallets)} airdrop wallet(s). Please select one to use:\n\n"
                f"💡 Showing most recent 5 wallets.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.SELECT_EXISTING_AIRDROP_WALLET
        
    except Exception as e:
        logger.error(
            f"Failed to load existing airdrop wallets for user {user.id}: {str(e)}",
            extra={"user_id": user.id}
        )
        
        keyboard = InlineKeyboardMarkup([
            [build_button("Try Again", "use_existing_airdrop_wallet")],
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await query.edit_message_text(
            format_pumpfun_error_message("airdrop_wallet_loading", str(e)),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLING_WALLET_SETUP


async def select_existing_airdrop_wallet(update: Update, context: CallbackContext) -> int:
    """
    Handle selection of a specific existing airdrop wallet.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    try:
        choice = query.data
        
        if choice == "back_to_bundling_setup":
            # Import the start_bundling_workflow function from start_handler
            from bot.handlers.start_handler import start_bundling_workflow
            # Return to bundling setup
            return await start_bundling_workflow(update, context)
        
        # Extract wallet index from callback data
        if choice.startswith("select_airdrop_"):
            wallet_index = int(choice.replace("select_airdrop_", ""))
            
            # Get available wallets from session
            available_wallets = session_manager.get_session_value(user.id, "available_airdrop_wallets", [])
            
            if wallet_index >= len(available_wallets):
                raise ValueError(f"Invalid wallet index: {wallet_index}")
            
            wallet_data = available_wallets[wallet_index]
            wallet_address = wallet_data["wallet_address"]
            
            # Store wallet information in session
            session_manager.update_session_value(user.id, "airdrop_wallet_address", wallet_address)
            # Store private key if available
            if wallet_data.get("private_key"):
                session_manager.update_session_value(user.id, "airdrop_private_key", wallet_data["private_key"])
            
            logger.info(
                f"Selected existing airdrop wallet {wallet_index} for user {user.id}",
                extra={"user_id": user.id, "wallet_address": wallet_address}
            )
            
            # Show success message and proceed
            keyboard = InlineKeyboardMarkup([
                [build_button("Continue", "continue_to_bundled_count")]
            ])
            
            created_date = wallet_data.get("created_at", "Unknown")
            wallet_type = "Imported" if wallet_data.get("imported") else "Created"
            
            await query.edit_message_text(
                f"✅ **Selected Airdrop Wallet**\n\n"
                f"**Address:** `{wallet_address}`\n"
                f"**Type:** {wallet_type}\n"
                f"**Created:** {created_date[:10] if created_date != 'Unknown' else created_date}\n\n"
                f"Ready to proceed with bundled wallet creation.",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.BUNDLED_WALLETS_COUNT
        
        else:
            raise ValueError(f"Unknown choice: {choice}")
        
    except Exception as e:
        logger.error(
            f"Failed to select existing airdrop wallet for user {user.id}: {str(e)}",
            extra={"user_id": user.id}
        )
        
        keyboard = InlineKeyboardMarkup([
            [build_button("Try Again", "use_existing_airdrop_wallet")],
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await query.edit_message_text(
            format_pumpfun_error_message("airdrop_wallet_selection", str(e)),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLING_WALLET_SETUP


async def bundle_operation_progress(update: Update, context: CallbackContext) -> int:
    """
    Handle bundle operation progress viewing and details display.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    try:
        choice = query.data
        
        if choice == "view_funding_details":
            # Show funding operation details
            funding_results = session_manager.get_session_value(user.id, "funding_results", {})
            
            if not funding_results:
                await query.edit_message_text(
                    "❌ **No Funding Details Available**\n\n"
                    "No funding operation results found in session.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ConversationState.WALLET_FUNDING_PROGRESS
            
            # Format funding details message
            successful = funding_results.get("successful_transfers", 0)
            failed = funding_results.get("failed_transfers", 0)
            total = successful + failed
            
            details_message = (
                f"💰 **Wallet Funding Details**\n\n"
                f"📊 **Summary:**\n"
                f"• Total wallets: {total}\n"
                f"• Successfully funded: {successful}\n"
                f"• Failed to fund: {failed}\n"
                f"• Success rate: {(successful/total)*100:.1f}%\n\n" if total > 0 else ""
            )
            
            if funding_results.get("bundle_id"):
                details_message += f"📦 **Bundle ID:** `{funding_results['bundle_id']}`\n"
            
            if funding_results.get("amount_per_wallet"):
                details_message += f"💵 **Amount per wallet:** {funding_results['amount_per_wallet']} SOL\n"
            
            keyboard = InlineKeyboardMarkup([
                [build_button("🚀 Continue to Token Creation", "create_token_final")],
                [build_button("« Back", "start_wallet_funding")]
            ])
            
            await query.edit_message_text(
                details_message,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.WALLET_FUNDING_PROGRESS
            
        elif choice == "view_transaction_details":
            # Show transaction details from token creation
            final_results = session_manager.get_session_value(user.id, "final_creation_results", {})
            
            if not final_results:
                await query.edit_message_text(
                    "❌ **No Transaction Details Available**\n\n"
                    "No token creation results found in session.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ConversationState.BUNDLE_OPERATION_COMPLETE
            
            # Format transaction details
            details_message = (
                f"📊 **Transaction Details**\n\n"
                f"🪙 **Token Address:** `{final_results.get('mint_address', 'N/A')}`\n"
                f"📦 **Bundle ID:** `{final_results.get('bundle_id', 'N/A')}`\n"
                f"⏱️ **Status:** {final_results.get('status', 'Unknown')}\n\n"
            )
            
            if final_results.get("transaction_signatures"):
                signatures = final_results["transaction_signatures"]
                details_message += f"📝 **Transaction Signatures:**\n"
                for i, sig in enumerate(signatures[:5]):  # Show first 5
                    details_message += f"• `{sig[:8]}...{sig[-8:]}`\n"
                if len(signatures) > 5:
                    details_message += f"• ... and {len(signatures) - 5} more\n"
            
            keyboard = InlineKeyboardMarkup([
                [build_button("🎉 Start New Bundle", "back_to_activities")],
                [build_button("« Back", "view_final_details")]
            ])
            
            await query.edit_message_text(
                details_message,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.BUNDLE_OPERATION_COMPLETE
            
        elif choice == "view_final_details":
            # Show final operation summary
            final_results = session_manager.get_session_value(user.id, "final_creation_results", {})
            buy_amounts = session_manager.get_session_value(user.id, "buy_amounts", {})
            wallet_group_counts = session_manager.get_session_value(user.id, "wallet_group_counts", {})
            
            if not final_results:
                await query.edit_message_text(
                    "❌ **No Final Details Available**\n\n"
                    "No operation results found in session.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ConversationState.BUNDLE_OPERATION_COMPLETE
            
            # Format final details message
            details_message = (
                f"🎉 **Operation Complete - Final Summary**\n\n"
                f"🪙 **Token Created:** `{final_results.get('mint_address', 'N/A')}`\n"
                f"📦 **Bundle ID:** `{final_results.get('bundle_id', 'N/A')}`\n"
                f"⏱️ **Status:** {final_results.get('status', 'Success')}\n\n"
            )
            
            # Add buy amounts summary
            if buy_amounts:
                details_message += f"💰 **Buy Amounts Executed:**\n"
                for group, amount in buy_amounts.items():
                    count = wallet_group_counts.get(group, 1)
                    total_spent = amount * count
                    details_message += f"• {group}: {amount} SOL × {count} = {total_spent} SOL\n"
                
                total_spent = sum(amount * wallet_group_counts.get(group, 1) for group, amount in buy_amounts.items())
                details_message += f"\n**Total SOL Spent:** {total_spent} SOL\n"
            
            keyboard = InlineKeyboardMarkup([
                [build_button("📊 View Transaction Details", "view_transaction_details")],
                [build_button("🎉 Start New Bundle", "back_to_activities")]
            ])
            
            await query.edit_message_text(
                details_message,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.BUNDLE_OPERATION_COMPLETE
            
        elif choice == "start_bundle_operations":
            # Start bundle operations (placeholder for future implementation)
            await query.edit_message_text(
                "🚀 **Bundle Operations**\n\n"
                "Bundle operations feature is under development. "
                "Please use the individual token creation workflow for now.",
                reply_markup=InlineKeyboardMarkup([
                    [build_button("« Back to Activities", "back_to_activities")]
                ]),
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.BUNDLE_OPERATION_PROGRESS
            
        else:
            # Unknown choice, redirect to activities
            logger.warning(f"Unknown bundle operation progress choice: {choice} from user {user.id}")
            
            # Import the start function from start_handler to redirect to activities
            from bot.handlers.start_handler import start
            return await start(update, context)
        
    except Exception as e:
        logger.error(
            f"Error in bundle operation progress for user {user.id}: {str(e)}",
            extra={"user_id": user.id, "choice": query.data},
            exc_info=True
        )
        
        keyboard = InlineKeyboardMarkup([
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await query.edit_message_text(
            format_pumpfun_error_message("bundle_operation_progress", str(e)),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLE_OPERATION_COMPLETE 


async def check_funding_prerequisites(update: Update, context: CallbackContext) -> int:
    """
    Check and display funding prerequisites to help users debug setup issues.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    try:
        # Check all required session data
        pumpfun_client = session_manager.get_session_value(user.id, "pumpfun_client")
        airdrop_wallet = session_manager.get_session_value(user.id, "airdrop_wallet_address")
        bundled_wallets_count = session_manager.get_session_value(user.id, "bundled_wallets_count")
        bundled_wallets = session_manager.get_session_value(user.id, "bundled_wallets")
        
        # Build prerequisites status message
        status_message = "🔍 **Funding Prerequisites Check**\n\n"
        
        # Check PumpFun client
        if pumpfun_client:
            status_message += "✅ **PumpFun API Client:** Connected\n"
        else:
            status_message += "❌ **PumpFun API Client:** Not found - restart workflow\n"
        
        # Check airdrop wallet
        if airdrop_wallet:
            status_message += f"✅ **Airdrop Wallet:** `{airdrop_wallet[:8]}...{airdrop_wallet[-8:]}`\n"
            
            # Try to check balance if client is available
            if pumpfun_client:
                try:
                    balance_info = pumpfun_client.get_wallet_balance(airdrop_wallet)
                    if "data" in balance_info and "balance" in balance_info["data"]:
                        current_balance = balance_info["data"]["balance"]
                    else:
                        current_balance = balance_info.get("balance", 0)
                    
                    status_message += f"   • **Balance:** {current_balance:.6f} SOL\n"
                    
                    if current_balance > 0.1:
                        status_message += "   • **Status:** ✅ Sufficient for funding\n"
                    else:
                        status_message += "   • **Status:** ⚠️ Low balance - may need more SOL\n"
                        
                except Exception as balance_error:
                    status_message += f"   • **Balance Check:** ❌ Failed - {str(balance_error)[:50]}...\n"
            
        else:
            status_message += "❌ **Airdrop Wallet:** Not configured\n"
        
        # Check bundled wallets count
        if bundled_wallets_count and bundled_wallets_count > 0:
            status_message += f"✅ **Bundled Wallets Count:** {bundled_wallets_count}\n"
        else:
            status_message += "❌ **Bundled Wallets Count:** Not set or zero\n"
        
        # Check actual bundled wallets
        if bundled_wallets and len(bundled_wallets) > 0:
            status_message += f"✅ **Bundled Wallets Created:** {len(bundled_wallets)} wallets\n"
            status_message += f"   • **First wallet:** `{bundled_wallets[0][:8]}...{bundled_wallets[0][-8:]}`\n"
            
            # Check for count mismatch
            if bundled_wallets_count and len(bundled_wallets) != bundled_wallets_count:
                status_message += f"   • ⚠️ **Count mismatch:** Expected {bundled_wallets_count}, found {len(bundled_wallets)}\n"
            
        else:
            status_message += "❌ **Bundled Wallets Created:** None found\n"
        
        # Provide next steps based on what's missing
        status_message += "\n💡 **Recommended Actions:**\n"
        
        if not pumpfun_client:
            status_message += "1. Restart the bundling workflow to initialize API client\n"
        elif not airdrop_wallet:
            status_message += "1. Create or import an airdrop wallet\n"
        elif not bundled_wallets or len(bundled_wallets) == 0:
                            status_message += "1. Create bundled wallets (2-50 wallets supported)\n"
        elif airdrop_wallet and pumpfun_client:
            status_message += "1. All prerequisites appear to be met\n"
            status_message += "2. Try the funding process again\n"
        
        # Determine appropriate keyboard based on status
        if pumpfun_client and airdrop_wallet and bundled_wallets and len(bundled_wallets) > 0:
            keyboard = InlineKeyboardMarkup([
                [build_button("🔄 Retry Funding", "start_wallet_funding")],
                [build_button("📊 Check Balance Again", "check_wallet_balance")],
                [build_button("« Back to Activities", "back_to_activities")]
            ])
        else:
            keyboard = InlineKeyboardMarkup([
                [build_button("🔄 Restart Setup", "back_to_activities")],
                [build_button("📋 Check Again", "check_funding_prerequisites")]
            ])
        
        await query.edit_message_text(
            status_message,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_FUNDING_REQUIRED
        
    except Exception as e:
        logger.error(
            f"Prerequisites check failed for user {user.id}: {str(e)}",
            extra={"user_id": user.id},
            exc_info=True
        )
        
        keyboard = InlineKeyboardMarkup([
            [build_button("🔄 Restart Setup", "back_to_activities")]
        ])
        
        await query.edit_message_text(
            f"❌ **Prerequisites Check Failed**\n\n"
            f"Error checking prerequisites: {str(e)}\n\n"
            f"Please restart the bundling workflow.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_FUNDING_REQUIRED

async def retry_wallet_import(update: Update, context: CallbackContext) -> int:
    """
    Retry the wallet import process after a failure.
    Phase 3 recovery mechanism.
    """
    user = get_user(update, context)
    query = get_query(update)
    
    try:
        await query.edit_message_text(
            "🔄 **Retrying Wallet Import**\n\n"
            "Attempting to import bundled wallets to the API again...\n\n"
            "Please wait while we retry the import process.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Call the main funding process which includes import
        return await start_wallet_funding(update, context)
        
    except Exception as e:
        logger.error(f"Retry wallet import failed for user {user.id}: {str(e)}")
        
        keyboard = InlineKeyboardMarkup([
            [build_button("« Back to Balance Check", "check_wallet_balance")],
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await query.edit_message_text(
            "❌ **Retry Import Failed**\n\n"
            f"The retry attempt also failed: {str(e)}\n\n"
            "Please check your wallet setup and try again from the beginning.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_FUNDING_REQUIRED

async def debug_wallet_data(update: Update, context: CallbackContext) -> int:
    """
    Debug wallet data to help diagnose import issues.
    Phase 3 recovery mechanism.
    """
    user = get_user(update, context)
    query = get_query(update)
    
    try:
        # Get wallet data from session
        bundled_wallets_data = session_manager.get_session_value(user.id, "bundled_wallets_data", {})
        bundled_wallets_original_json = session_manager.get_session_value(user.id, "bundled_wallets_original_json", None)
        
        debug_info = []
        debug_info.append("🔍 **Wallet Data Debug Information**\n")
        
        # Check session data
        if bundled_wallets_data:
            wallets_to_import = bundled_wallets_data.get("data", [])
            debug_info.append(f"✅ Session data found: {len(wallets_to_import)} wallets")
            
            # Check first wallet structure
            if wallets_to_import:
                first_wallet = wallets_to_import[0]
                required_fields = ["name", "privateKey"]
                missing_fields = [field for field in required_fields if field not in first_wallet]
                
                if missing_fields:
                    debug_info.append(f"❌ Missing fields in wallet data: {missing_fields}")
                else:
                    debug_info.append("✅ Wallet data structure looks correct")
                    debug_info.append(f"   • Name: {first_wallet.get('name', 'N/A')}")
                    debug_info.append(f"   • Has privateKey: {bool(first_wallet.get('privateKey'))}")
            else:
                debug_info.append("❌ No wallets found in session data")
        else:
            debug_info.append("❌ No bundled wallet data found in session")
        
        # Check file data
        if bundled_wallets_original_json:
            debug_info.append(f"✅ Original JSON data available")
        else:
            debug_info.append("❌ No original JSON data found")
        
        # Add recommendations
        debug_info.append("\n**Recommendations:**")
        if not bundled_wallets_data:
            debug_info.append("• Recreate bundled wallets from scratch")
        elif not wallets_to_import:
            debug_info.append("• Check wallet creation process")
        else:
            debug_info.append("• Wallet data appears valid - try import again")
            debug_info.append("• Check API server status")
        
        keyboard = InlineKeyboardMarkup([
            [build_button("🔄 Retry Import", "retry_wallet_import")],
            [build_button("🔄 Recreate Wallets", "retry_bundled_wallets")],
            [build_button("« Back to Balance Check", "check_wallet_balance")]
        ])
        
        await query.edit_message_text(
            "\n".join(debug_info),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_FUNDING_REQUIRED
        
    except Exception as e:
        logger.error(f"Debug wallet data failed for user {user.id}: {str(e)}")
        
        keyboard = InlineKeyboardMarkup([
            [build_button("« Back to Balance Check", "check_wallet_balance")]
        ])
        
        await query.edit_message_text(
            "❌ **Debug Failed**\n\n"
            f"Could not retrieve debug information: {str(e)}",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_FUNDING_REQUIRED

async def check_api_status(update: Update, context: CallbackContext) -> int:
    """
    Check the API server status and connectivity.
    Phase 3 recovery mechanism.
    """
    user = get_user(update, context)
    query = get_query(update)
    
    try:
        await query.edit_message_text(
            "🔍 **Checking API Status**\n\n"
            "Testing connection to the PumpFun API server...\n\n"
            "This may take a moment.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Get PumpFun client from session for health check
        pumpfun_client = session_manager.get_session_value(user.id, "pumpfun_client")
        if not pumpfun_client:
            status_info.append("❌ **PumpFun Client: NOT AVAILABLE**")
            status_info.append("   • Client not found in session - restart workflow")
            
            keyboard = InlineKeyboardMarkup([
                [build_button("🔄 Restart Workflow", "back_to_activities")],
                [build_button("« Back to Balance Check", "check_wallet_balance")]
            ])
            
            await query.edit_message_text(
                "\n".join(status_info),
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationState.WALLET_FUNDING_REQUIRED
        
        # Perform API health check
        health_result = pumpfun_client.health_check()
        
        status_info = []
        status_info.append("📊 **API Status Report**\n")
        
        # Parse health check results
        if health_result.get("status") == "healthy":
            status_info.append("✅ **API Server: HEALTHY**")
            status_info.append(f"   • API reachable: {health_result.get('api_reachable', 'Unknown')}")
            if health_result.get("cold_start_detected"):
                status_info.append("   • Cold start detected (longer initial response times)")
            
        elif health_result.get("status") == "unhealthy":
            status_info.append("❌ **API Server: UNHEALTHY**")
            status_info.append(f"   • Error: {health_result.get('error', 'Unknown error')}")
            if health_result.get("cold_start_likely"):
                status_info.append("   • Likely cause: Cold start (server sleeping)")
                status_info.append("   • Recommendation: Wait 30 seconds and try again")
        
        # Test wallet verification
        try:
            verification_result = pumpfun_client.verify_bundled_wallets_exist()
            status_info.append(f"\n✅ **Wallet Verification: WORKING**")
            status_info.append(f"   • Wallets exist: {verification_result.get('wallets_exist', 'Unknown')}")
            status_info.append(f"   • Method: {verification_result.get('verification_method', 'Unknown')}")
        except Exception as verify_error:
            status_info.append(f"\n❌ **Wallet Verification: FAILED**")
            status_info.append(f"   • Error: {str(verify_error)}")
        
        keyboard = InlineKeyboardMarkup([
            [build_button("🔄 Retry Import", "retry_wallet_import")],
            [build_button("⏱️ Wait & Retry", "wait_and_retry_import")], 
            [build_button("« Back to Balance Check", "check_wallet_balance")]
        ])
        
        await query.edit_message_text(
            "\n".join(status_info),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_FUNDING_REQUIRED
        
    except Exception as e:
        logger.error(f"API status check failed for user {user.id}: {str(e)}")
        
        keyboard = InlineKeyboardMarkup([
            [build_button("🔄 Try Again", "check_api_status")],
            [build_button("« Back to Balance Check", "check_wallet_balance")]
        ])
        
        await query.edit_message_text(
            "❌ **Status Check Failed**\n\n"
            f"Could not check API status: {str(e)}\n\n"
            "The API server may be temporarily unavailable.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_FUNDING_REQUIRED

async def wait_and_retry_import(update: Update, context: CallbackContext) -> int:
    """
    Wait for potential cold start to resolve, then retry import.
    Phase 3 recovery mechanism for cold start scenarios.
    """
    user = get_user(update, context)
    query = get_query(update)
    
    try:
        # Show waiting message
        await query.edit_message_text(
            "⏱️ **Waiting for API Wake-up**\n\n"
            "The API server may be in cold start mode.\n"
            "Waiting 30 seconds for the server to fully initialize...\n\n"
            "🔄 Please wait...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Wait for cold start resolution
        import asyncio
        await asyncio.sleep(30)
        
        # Update message
        await query.edit_message_text(
            "🔄 **Retrying Import After Wait**\n\n"
            "The wait period is complete.\n"
            "Now retrying the wallet import process...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Retry the import
        return await start_wallet_funding(update, context)
        
    except Exception as e:
        logger.error(f"Wait and retry import failed for user {user.id}: {str(e)}")
        
        keyboard = InlineKeyboardMarkup([
            [build_button("🔄 Try Again", "retry_wallet_import")],
            [build_button("« Back to Balance Check", "check_wallet_balance")]
        ])
        
        await query.edit_message_text(
            "❌ **Wait and Retry Failed**\n\n"
            f"The retry after waiting also failed: {str(e)}\n\n"
            "Please try again or return to balance check.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_FUNDING_REQUIRED

async def back_to_bundled_setup(update: Update, context: CallbackContext) -> int:
    """
    Return to bundled wallet setup process.
    Phase 3 recovery mechanism.
    """
    user = get_user(update, context)
    query = get_query(update)
    
    try:
        await query.edit_message_text(
            "🔄 **Returning to Bundled Wallet Setup**\n\n"
            "You will now be taken back to the bundled wallet creation process.\n\n"
            "This will create fresh bundled wallets.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Clear existing wallet data to start fresh
        session_manager.update_session_value(user.id, "bundled_wallets_data", None)
        session_manager.update_session_value(user.id, "bundled_wallets_original_json", None)
        
        # Return to bundled wallet count selection
        return await bundled_wallets_count(update, context)
        
    except Exception as e:
        logger.error(f"Back to bundled setup failed for user {user.id}: {str(e)}")
        
        keyboard = InlineKeyboardMarkup([
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await query.edit_message_text(
            "❌ **Navigation Failed**\n\n"
            f"Could not return to bundled wallet setup: {str(e)}",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLED_WALLETS_COUNT

async def check_bundled_wallets_funding_status(pumpfun_client, bundled_wallets_count: int, buy_amounts: Dict[str, float], user_id: int, airdrop_wallet_address: str) -> Dict[str, Any]:
    """
    Check if bundled wallets have sufficient funding by checking individual wallet balances.
    Now uses proper API minimum balance requirements.
    
    Args:
        pumpfun_client: PumpFun client instance
        bundled_wallets_count: Number of bundled wallets
        buy_amounts: Dictionary containing buy amounts for each wallet type
        user_id: User ID for loading user-specific wallets
        airdrop_wallet_address: Airdrop wallet address for loading associated bundled wallets
        
    Returns:
        Dictionary with funding status
    """
    try:
        # Load bundled wallet data for this specific user and airdrop wallet
        bundled_wallets_data = bundled_wallet_storage.load_bundled_wallets(airdrop_wallet_address, user_id)
        
        if not bundled_wallets_data:
            return {
                "all_funded": False,
                "funded_count": 0,
                "error": f"No bundled wallets found for user {user_id} with airdrop wallet {airdrop_wallet_address[:8]}..."
            }
        
        # Calculate required balances per API documentation:
        # - DevWallet (tipper): 0.055 SOL minimum + buy amount  
        # - Other wallets: 0.025 SOL minimum + buy amount
        dev_wallet_buy_amount = buy_amounts.get("DevWallet", 0.01)
        first_bundled_buy_amount = buy_amounts.get("First Bundled Wallets", 0.01)
        
        dev_wallet_required = 0.055 + dev_wallet_buy_amount
        bundled_wallet_required = 0.025 + first_bundled_buy_amount
        
        funded_count = 0
        total_wallets = len(bundled_wallets_data)
        balance_check_errors = []
        insufficient_wallets = []
        
        logger.info(f"Checking SOL balance for {total_wallets} bundled wallets with API requirements")
        
        # Check each wallet's SOL balance using enhanced API endpoint
        for wallet in bundled_wallets_data:
            # Use normalized address field (bundled_wallet_storage returns normalized structure)
            wallet_address = wallet.get("address") or wallet.get("publicKey")
            wallet_name = wallet.get("name", "Unknown")
            
            if not wallet_address:
                continue
                
            try:
                # Use enhanced SOL balance endpoint
                balance_response = pumpfun_client.get_wallet_sol_balance(wallet_address)
                
                # Extract SOL balance from enhanced response format
                sol_balance = 0
                if "data" in balance_response and "sol" in balance_response["data"]:
                    sol_balance = balance_response["data"]["sol"].get("balance", 0)
                elif "data" in balance_response:
                    # Fallback for legacy format
                    sol_balance = balance_response["data"].get("balance", 0)
                
                # Determine required balance based on wallet role
                if wallet_name == "DevWallet":
                    required_balance = dev_wallet_required
                    logger.info(f"Wallet {wallet_name} ({wallet_address[:8]}...): {sol_balance:.6f} SOL (DevWallet requires {required_balance:.6f} SOL)")
                else:
                    required_balance = bundled_wallet_required
                    logger.info(f"Wallet {wallet_name} ({wallet_address[:8]}...): {sol_balance:.6f} SOL (Bundled wallet requires {required_balance:.6f} SOL)")
                
                if sol_balance >= required_balance:
                    funded_count += 1
                else:
                    insufficient_wallets.append({
                        "name": wallet_name,
                        "address": wallet_address,
                        "current": sol_balance,
                        "required": required_balance,
                        "shortfall": required_balance - sol_balance
                    })
                    
            except Exception as e:
                logger.error(f"Error checking balance for wallet {wallet_name}: {e}")
                balance_check_errors.append(f"{wallet_name}: {str(e)}")
                insufficient_wallets.append({
                    "name": wallet_name,
                    "address": wallet_address,
                    "current": 0,
                    "required": bundled_wallet_required if wallet_name != "DevWallet" else dev_wallet_required,
                    "shortfall": bundled_wallet_required if wallet_name != "DevWallet" else dev_wallet_required,
                    "error": str(e)
                })
        
        all_funded = funded_count == total_wallets
        
        logger.info(f"Bundled wallet funding status: {funded_count}/{total_wallets} wallets funded")
        
        return {
            "all_funded": all_funded,
            "funded_count": funded_count,
            "total_wallets": total_wallets,
            "dev_wallet_required": dev_wallet_required,
            "bundled_wallet_required": bundled_wallet_required,
            "insufficient_wallets": insufficient_wallets,
            "balance_check_errors": balance_check_errors if balance_check_errors else None
        }
        
    except Exception as e:
        logger.error(f"Error checking bundled wallets funding status: {e}")
        return {
            "all_funded": False,
            "funded_count": 0,
            "error": str(e)
        }