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
    format_buy_amounts_preview
)
from bot.state.session_manager import session_manager

# Specialized handler imports
from .wallet_handler import (
    create_airdrop_wallet, 
    wait_and_retry_airdrop, 
    import_airdrop_wallet, 
    process_airdrop_wallet_import, 
    continue_to_bundled_wallets_setup, 
    bundled_wallets_count,
    check_wallet_balance,
    fund_bundled_wallets_now,
    start_wallet_funding,
    retry_wallet_funding,
    return_funds_confirmation,
    execute_return_funds,
    return_funds_complete,
    use_existing_airdrop_wallet,
    select_existing_airdrop_wallet
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
    create_token_final
)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_user(update: Update, context: CallbackContext):
    """Helper function to get user from update object."""
    if update.callback_query:
        return update.callback_query.from_user
    elif update.message:
        return update.message.from_user
    else:
        raise ValueError("Update object must have either callback_query or message")


def get_query(update: Update):
    """Helper function to get query from update object."""
    return update.callback_query if update.callback_query else None


# =============================================================================
# ORCHESTRATION FUNCTIONS - Core workflow coordination
# =============================================================================

async def token_creation_start(update: Update, context: CallbackContext) -> int:
    """
    Start the token creation parameter collection process.
    Orchestrator function that delegates to token_config_handler.
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


# =============================================================================
# BUY AMOUNTS CONFIGURATION - Core orchestration logic
# =============================================================================

async def configure_buy_amounts(update: Update, context: CallbackContext) -> int:
    """
    Start buy amounts configuration process after token preview.
    Core orchestration function for buy amounts workflow.
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Get total bundled wallets count from session
    bundled_wallets_count = session_manager.get_session_value(user.id, "bundled_wallets_count", 0)
    
    # Initialize buy amounts configuration for wallet groups
    wallet_groups = ["DevWallet"]
    
    if bundled_wallets_count > 0:
        wallet_groups.append("First Bundled Wallets")
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
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Get wallet groups from session
    wallet_groups = session_manager.get_session_value(user.id, "buy_amounts_wallet_groups")
    
    if not wallet_groups:
        await query.edit_message_text("❌ **Configuration Error**\n\nWallet groups not found. Please restart the configuration.")
        return ConversationState.TOKEN_CREATION_PREVIEW
    
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
    """
    user = update.message.from_user
    amount_input = update.message.text.strip()
    
    # Get current configuration
    wallet_groups = session_manager.get_session_value(user.id, "buy_amounts_wallet_groups")
    current_index = session_manager.get_session_value(user.id, "current_buy_group_index")
    buy_amounts = session_manager.get_session_value(user.id, "buy_amounts") or {}
    wallet_group_counts = session_manager.get_session_value(user.id, "wallet_group_counts") or {}
    
    if not wallet_groups or current_index is None:
        await update.message.reply_text("❌ **Configuration Error**\n\nSession data not found. Please restart the configuration.")
        return ConversationState.TOKEN_CREATION_PREVIEW
    
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
            f"❌ **Invalid Amount**\n\n{amount_or_error}\n\nPlease try again:",
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
                wallet_groups[next_index],
                next_index + 1,
                len(wallet_groups),
                group_descriptions.get(wallet_groups[next_index], "")
            ),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUY_AMOUNTS_INPUT
    else:
        # All wallet groups configured, show preview
        keyboard = InlineKeyboardMarkup([
            [build_button("✅ Proceed to Balance Check", "check_wallet_balance")],
            [build_button("✏️ Edit Buy Amounts", "edit_buy_amounts")],
            [build_button("« Back to Token Preview", "back_to_token_preview")]
        ])
        
        await update.message.reply_text(
            format_buy_amounts_preview(buy_amounts, wallet_group_counts),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUY_AMOUNTS_PREVIEW


async def edit_buy_amounts(update: Update, context: CallbackContext) -> int:
    """
    Allow user to edit buy amounts by restarting the configuration.
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Reset buy amounts configuration
    return await configure_buy_amounts(update, context)


# =============================================================================
# OPERATION PROGRESS FUNCTIONS - Bundle operation monitoring and details
# =============================================================================

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
            f"❌ **Operation Error**\n\n"
            f"An error occurred while viewing operation details: {str(e)}\n\n"
            f"Please try again or return to activities.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLE_OPERATION_COMPLETE


# =============================================================================
# MAIN ORCHESTRATOR FUNCTIONS
# =============================================================================

# Import token trading operations from dedicated handler
from .token_trading_handler import (
    bundler_management_choice,
    show_token_list,
    token_selection,
    token_operation_choice,
    back_to_token_options
)

# Note: The actual ConversationHandler assembly would be added here
# This is where all the handlers from different modules get wired together
# into the complete workflow. This keeps the orchestration logic centralized
# while the business logic remains in specialized handlers.

logger.info("Bundling handler orchestrator loaded with modular architecture")
