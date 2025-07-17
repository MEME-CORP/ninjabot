"""
Token Trading Handler

This module handles post-creation token trading operations for PumpFun tokens.
It provides functionality to buy and sell tokens with dev and bundled wallets.

Architecture:
- Separated from bundling_handler to maintain single responsibility
- Handles token management operations after creation
- Integrates with existing token storage and session management
"""

from typing import Dict, List, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext
from loguru import logger

# Bot configuration and utilities
from bot.config import ConversationState, CallbackPrefix
from bot.utils.keyboard_utils import build_button
from bot.utils.message_utils import (
    format_bundler_management_selection_message,
    format_token_list_message,
    format_token_management_options_message,
    format_sell_percentage_selection_message,
    format_sell_confirmation_message,
    format_sell_operation_progress,
    format_sell_operation_results
)
from bot.state.session_manager import session_manager
from bot.utils.token_storage import token_storage
from bot.api.api_client import api_client
from bot.api.pumpfun_client import PumpFunClient  # Added for token trading operations
from bot.utils.wallet_storage import airdrop_wallet_storage, bundled_wallet_storage


# =============================================================================
# BUNDLER MANAGEMENT FUNCTIONS - Token management operations
# =============================================================================

async def bundler_management_choice(update: Update, context: CallbackContext) -> int:
    """
    Handle bundler management choice (view tokens, etc.).
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    
    if choice == "view_tokens":
        return await show_airdrop_wallet_selection(update, context)
    elif choice == "back_to_activities":
        # Import and redirect to activity selection
        from .start_handler import start
        return await start(update, context)
    else:
        logger.warning(f"Unknown bundler management choice: {choice} from user {user.id}")
        return ConversationState.BUNDLER_MANAGEMENT


async def show_token_list(update: Update, context: CallbackContext) -> int:
    """
    Show list of user's created tokens for management.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
    # Get user's tokens
    user_tokens = token_storage.get_user_tokens(user.id)
    
    if not user_tokens:
        keyboard = [[build_button("« Back to Wallet Overview", "back_to_wallet_overview")]]
        
        await query.edit_message_text(
            "📭 **No Tokens Found**\n\n"
            "You haven't created any tokens yet.\n\n"
            "Use 'Token Bundling (PumpFun)' to create your first token!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_BALANCE_OVERVIEW
    
    # Build keyboard with token options (max 10 tokens)
    keyboard = []
    for i, token in enumerate(user_tokens[:10]):
        token_name = token.get('token_name', f'Token {i+1}')
        # Truncate long names for button display
        display_name = token_name[:25] + "..." if len(token_name) > 25 else token_name
        keyboard.append([build_button(f"🪙 {display_name}", f"{CallbackPrefix.TOKEN_SELECT}{i}")])
    
    # Add navigation buttons
    keyboard.append([build_button("« Back to Wallet Overview", "back_to_wallet_overview")])
    
    # Store tokens in session for later reference
    session_manager.update_session_value(user.id, "management_tokens", user_tokens)
    
    await query.edit_message_text(
        format_token_list_message(user_tokens),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.TOKEN_LIST


async def token_selection(update: Update, context: CallbackContext) -> int:
    """
    Handle token selection for management operations.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    
    if choice == "back_to_bundler_mgmt":
        # Go back to airdrop wallet selection (updated flow)
        return await show_airdrop_wallet_selection(update, context)
    elif choice == "back_to_wallet_overview":
        # Go back to wallet balance overview
        selected_airdrop_wallet = session_manager.get_session_value(user.id, "selected_airdrop_wallet")
        if selected_airdrop_wallet:
            return await show_wallet_balance_overview(update, context, selected_airdrop_wallet)
        else:
            return await show_airdrop_wallet_selection(update, context)
    
    # Extract token index from callback data
    if choice.startswith(CallbackPrefix.TOKEN_SELECT):
        try:
            token_index = int(choice.replace(CallbackPrefix.TOKEN_SELECT, ""))
            
            # Get tokens from session
            management_tokens = session_manager.get_session_value(user.id, "management_tokens", [])
            
            if 0 <= token_index < len(management_tokens):
                selected_token = management_tokens[token_index]
                
                # Store selected token in session
                session_manager.update_session_value(user.id, "selected_token", selected_token)
                
                return await show_token_management_options(update, context, selected_token)
            else:
                logger.error(f"Invalid token index {token_index} for user {user.id}")
                return ConversationState.TOKEN_LIST
                
        except ValueError:
            logger.error(f"Invalid token selection format: {choice} from user {user.id}")
            return ConversationState.TOKEN_LIST
    
    return ConversationState.TOKEN_LIST


async def show_token_management_options(update: Update, context: CallbackContext, token_data: Dict[str, Any]) -> int:
    """
    Show management options for selected token.
    
    Args:
        update: The update object
        context: The context object
        token_data: Selected token data
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
    # Build operation keyboard
    keyboard = [
        [build_button("🟢 Buy with Dev Wallet", f"{CallbackPrefix.TOKEN_OPERATION}buy_dev")],
        [build_button("🟢 Buy with Bundled Wallets", f"{CallbackPrefix.TOKEN_OPERATION}buy_bundled")],
        [build_button("🟢 Buy with All Wallets", f"{CallbackPrefix.TOKEN_OPERATION}buy_all")],
        [build_button("🔴 Sell with Dev Wallet", f"{CallbackPrefix.TOKEN_OPERATION}sell_dev")],
        [build_button("🔴 Sell with Bundled Wallets", f"{CallbackPrefix.TOKEN_OPERATION}sell_bundled")],
        [build_button("🔴 Sell with All Wallets", f"{CallbackPrefix.TOKEN_OPERATION}sell_all")],
        [build_button("« Back to Token List", "back_to_token_list")]
    ]
    
    await query.edit_message_text(
        format_token_management_options_message(token_data),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.TOKEN_MANAGEMENT_OPTIONS


async def token_operation_choice(update: Update, context: CallbackContext) -> int:
    """
    Handle token trading operation choice.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    
    if choice == "back_to_token_list":
        return await show_token_list(update, context)
    
    # Handle trading operations
    if choice.startswith(CallbackPrefix.TOKEN_OPERATION):
        operation = choice.replace(CallbackPrefix.TOKEN_OPERATION, "")
        
        # Get selected token from session
        selected_token = session_manager.get_session_value(user.id, "selected_token")
        
        if not selected_token:
            logger.error(f"No selected token found for user {user.id}")
            return ConversationState.TOKEN_LIST
        
        # Store operation type in session
        session_manager.update_session_value(user.id, "token_operation", operation)
        
        # Handle sell operations with percentage selection
        if operation.startswith("sell_"):
            return await show_sell_percentage_selection(update, context, selected_token, operation)
        
        # Handle buy operations (placeholder for now)
        elif operation.startswith("buy_"):
            keyboard = [[build_button("« Back to Token Options", "back_to_token_options")]]
            
            operation_text = {
                "buy_dev": "🟢 **Buy with Dev Wallet**",
                "buy_bundled": "🟢 **Buy with Bundled Wallets**", 
                "buy_all": "🟢 **Buy with All Wallets**"
            }.get(operation, "Unknown Operation")
            
            token_name = selected_token.get('token_name', 'Unknown Token')
            
            await query.edit_message_text(
                f"{operation_text}\n\n"
                f"**Token:** {token_name}\n\n"
                f"� **Coming Soon**\n\n"
                f"This trading operation will be implemented in the next update. "
                f"The system will execute {operation.replace('_', ' ')} operations for your selected token.\n\n"
                f"Features will include:\n"
                f"• Amount configuration\n"
                f"• Batch transaction handling\n"
                f"• Real-time status updates\n"
                f"• Success/failure reporting",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.TOKEN_TRADING_OPERATION
    
    return ConversationState.TOKEN_MANAGEMENT_OPTIONS


async def show_sell_percentage_selection(update: Update, context: CallbackContext, 
                                       token_data: Dict[str, Any], operation: str) -> int:
    """
    Show sell percentage selection options.
    
    Args:
        update: The update object
        context: The context object
        token_data: Selected token data
        operation: Sell operation type
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
    # Build percentage selection keyboard
    keyboard = [
        [
            build_button("25%", f"{CallbackPrefix.SELL_PERCENTAGE}25"),
            build_button("50%", f"{CallbackPrefix.SELL_PERCENTAGE}50")
        ],
        [
            build_button("75%", f"{CallbackPrefix.SELL_PERCENTAGE}75"),
            build_button("100%", f"{CallbackPrefix.SELL_PERCENTAGE}100")
        ],
        [build_button("📝 Custom Percentage", f"{CallbackPrefix.SELL_PERCENTAGE}custom")],
        [build_button("« Back to Token Options", "back_to_token_options")]
    ]
    
    await query.edit_message_text(
        format_sell_percentage_selection_message(token_data, operation),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.SELL_PERCENTAGE_SELECTION


async def sell_percentage_choice(update: Update, context: CallbackContext) -> int:
    """
    Handle sell percentage selection.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    
    if choice == "back_to_token_options":
        selected_token = session_manager.get_session_value(user.id, "selected_token")
        if selected_token:
            return await show_token_management_options(update, context, selected_token)
        else:
            return await show_token_list(update, context)
    
    # Handle percentage selection
    if choice.startswith(CallbackPrefix.SELL_PERCENTAGE):
        percentage_str = choice.replace(CallbackPrefix.SELL_PERCENTAGE, "")
        
        if percentage_str == "custom":
            # For custom percentage, we'd need to handle text input
            # For now, show a message asking user to select from predefined options
            keyboard = [[build_button("« Back to Percentage Selection", "back_to_percentage_selection")]]
            
            await query.edit_message_text(
                "📝 **Custom Percentage**\n\n"
                "Custom percentage input is not yet implemented.\n\n"
                "Please use one of the predefined percentage options (25%, 50%, 75%, 100%) for now.\n\n"
                "This feature will be added in a future update.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.SELL_PERCENTAGE_SELECTION
        
        else:
            try:
                sell_percentage = float(percentage_str)
                
                # Store sell percentage in session
                session_manager.update_session_value(user.id, "sell_percentage", sell_percentage)
                
                # Show confirmation
                return await show_sell_confirmation(update, context, sell_percentage)
                
            except ValueError:
                logger.error(f"Invalid percentage format: {percentage_str} from user {user.id}")
                return ConversationState.SELL_PERCENTAGE_SELECTION
    
    elif choice == "back_to_percentage_selection":
        selected_token = session_manager.get_session_value(user.id, "selected_token")
        operation = session_manager.get_session_value(user.id, "token_operation")
        if selected_token and operation:
            return await show_sell_percentage_selection(update, context, selected_token, operation)
    
    return ConversationState.SELL_PERCENTAGE_SELECTION


async def show_sell_confirmation(update: Update, context: CallbackContext, sell_percentage: float) -> int:
    """
    Show sell operation confirmation.
    
    Args:
        update: The update object
        context: The context object
        sell_percentage: Selected sell percentage
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
    # Get session data
    selected_token = session_manager.get_session_value(user.id, "selected_token")
    operation = session_manager.get_session_value(user.id, "token_operation")
    
    if not selected_token or not operation:
        logger.error(f"Missing session data for user {user.id}")
        return ConversationState.TOKEN_LIST
    
    # Build confirmation keyboard
    keyboard = [
        [
            build_button("✅ Confirm & Execute", "confirm_sell_execute"),
            build_button("❌ Cancel", "cancel_sell")
        ],
        [build_button("« Change Percentage", "back_to_percentage_selection")]
    ]
    
    await query.edit_message_text(
        format_sell_confirmation_message(selected_token, operation, sell_percentage),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.SELL_CONFIRM_EXECUTE


async def sell_confirmation_choice(update: Update, context: CallbackContext) -> int:
    """
    Handle sell confirmation choice.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    
    if choice == "confirm_sell_execute":
        return await execute_sell_operation(update, context)
    
    elif choice == "cancel_sell":
        selected_token = session_manager.get_session_value(user.id, "selected_token")
        if selected_token:
            return await show_token_management_options(update, context, selected_token)
        else:
            return await show_token_list(update, context)
    
    elif choice == "back_to_percentage_selection":
        selected_token = session_manager.get_session_value(user.id, "selected_token")
        operation = session_manager.get_session_value(user.id, "token_operation")
        if selected_token and operation:
            return await show_sell_percentage_selection(update, context, selected_token, operation)
    
    return ConversationState.SELL_CONFIRM_EXECUTE


async def execute_sell_operation(update: Update, context: CallbackContext) -> int:
    """
    Execute the sell operation based on user selections.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
    # Get session data
    selected_token = session_manager.get_session_value(user.id, "selected_token")
    operation = session_manager.get_session_value(user.id, "token_operation")
    sell_percentage = session_manager.get_session_value(user.id, "sell_percentage")
    
    if not all([selected_token, operation, sell_percentage]):
        logger.error(f"Missing session data for sell execution, user {user.id}")
        return ConversationState.TOKEN_LIST
    
    # Show progress message
    progress_data = {
        'operation_type': f'Sell {sell_percentage}% Tokens',
        'current_step': 'Preparing sell transaction...',
        'completed_operations': 0,
        'total_operations': 1 if operation == "sell_dev" else 2 if operation == "sell_all" else 1
    }
    
    await query.edit_message_text(
        format_sell_operation_progress(progress_data),
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        mint_address = selected_token.get('mint_address')
        slippage_bps = 2500  # 25% slippage
        
        # Get wallet data - use selected airdrop wallet from new flow
        selected_airdrop_wallet = session_manager.get_session_value(user.id, "selected_airdrop_wallet")
        airdrop_address = None
        
        # Method 1: Use selected airdrop wallet from new flow (preferred)
        if selected_airdrop_wallet and 'address' in selected_airdrop_wallet:
            airdrop_address = selected_airdrop_wallet['address']
            logger.info(f"Using selected airdrop wallet: {airdrop_address[:8]}...")
        
        # Method 2: Fallback to session airdrop wallet (legacy support)
        if not airdrop_address:
            session_data = session_manager.get_session_data(user.id)
            airdrop_wallet = session_data.get('airdrop_wallet')
            if airdrop_wallet and 'address' in airdrop_wallet:
                airdrop_address = airdrop_wallet['address']
                logger.info(f"Found airdrop wallet in session: {airdrop_address[:8]}...")
        
        # Method 3: Try to get airdrop address from token record
        if not airdrop_address and 'airdrop_wallet_address' in selected_token:
            airdrop_address = selected_token['airdrop_wallet_address']
            logger.info(f"Found airdrop wallet in token record: {airdrop_address[:8]}...")
        
        # Method 4: Search for wallets by user ID (fallback)
        if not airdrop_address:
            user_bundled_wallets = bundled_wallet_storage.list_user_bundled_wallets(user.id)
            if user_bundled_wallets:
                # Use the most recent wallet
                latest_wallet = max(user_bundled_wallets, key=lambda x: x.get('timestamp', 0))
                airdrop_address = latest_wallet.get('airdrop_wallet_address')
                if airdrop_address:
                    logger.info(f"Found airdrop wallet via user search: {airdrop_address[:8]}...")
        
        if not airdrop_address:
            raise Exception("Could not find airdrop wallet address for this token")
        
        # Load bundled wallets from storage
        bundled_wallets = bundled_wallet_storage.load_bundled_wallets(airdrop_address, user.id)
        
        if not bundled_wallets:
            raise Exception(f"No bundled wallets found for airdrop address: {airdrop_address[:8]}...")
        
        logger.info(f"Loaded {len(bundled_wallets)} wallets for sell operation")
            
        logger.info(f"Loaded {len(bundled_wallets)} wallets for sell operation")
        
        # Prepare wallets for API call
        wallets_data = []
        
        # Add DevWallet first (if needed for the operation)
        if operation in ["sell_dev", "sell_all"]:
            dev_wallet = next((w for w in bundled_wallets if w.get('name') == 'DevWallet'), None)
            if dev_wallet and 'private_key' in dev_wallet:
                wallets_data.append({
                    "name": dev_wallet['name'],
                    "privateKey": dev_wallet['private_key']
                })
                logger.info(f"Added DevWallet to sell operation")
        
        # Add bundled wallets (if needed for the operation)
        if operation in ["sell_bundled", "sell_all"]:
            for wallet in bundled_wallets:
                if wallet.get('name') != 'DevWallet' and 'private_key' in wallet:
                    wallets_data.append({
                        "name": wallet['name'],
                        "privateKey": wallet['private_key']
                    })
            logger.info(f"Added {len([w for w in wallets_data if w['name'] != 'DevWallet'])} bundled wallets to sell operation")
        
        if not wallets_data:
            # No wallets found - show error
            keyboard = [[build_button("« Back to Token Options", "back_to_token_options")]]
            
            await query.edit_message_text(
                f"❌ **No Wallets Found**\n\n"
                f"Could not find wallet credentials for this token.\n\n"
                f"**Possible reasons:**\n"
                f"• Wallets were not created during token bundling\n"
                f"• Wallet storage files are missing or corrupted\n"
                f"• This token was created outside the bundling system\n\n"
                f"Please create a new token through the bundling system to enable trading operations.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.TOKEN_TRADING_OPERATION
        
        # Execute the sell operations based on operation type
        results = {}
        
        # Initialize PumpFun client for trading operations
        pumpfun_client = PumpFunClient()
        
        if operation == "sell_dev":
            # Sell with DevWallet only
            progress_data['current_step'] = 'Executing DevWallet sell...'
            await query.edit_message_text(
                format_sell_operation_progress(progress_data),
                parse_mode=ParseMode.MARKDOWN
            )
            
            dev_wallets = [w for w in wallets_data if w['name'] == 'DevWallet']
            if dev_wallets:
                # Extract dev wallet credentials for PumpFun API
                dev_wallet = dev_wallets[0]
                logger.info(f"Starting DevWallet sell for mint {mint_address} with {sell_percentage}% of tokens")
                
                results = pumpfun_client.sell_dev_wallet(
                    dev_wallet_private_key=dev_wallet.get('privateKey'),
                    mint_address=mint_address,
                    sell_percentage=sell_percentage,
                    slippage_bps=slippage_bps
                )
                
                logger.info(f"DevWallet sell completed successfully: {results}")
            else:
                raise Exception("DevWallet not found in wallet data")
        
        elif operation == "sell_bundled":
            # Sell with bundled wallets only (excluding DevWallet)
            progress_data['current_step'] = 'Executing batch sell...'
            await query.edit_message_text(
                format_sell_operation_progress(progress_data),
                parse_mode=ParseMode.MARKDOWN
            )
            
            bundled_wallets_only = [w for w in wallets_data if w['name'] != 'DevWallet']
            if bundled_wallets_only:
                # Pass complete wallet objects to PumpFun API for correct naming
                results = pumpfun_client.batch_sell_token(
                    wallets=bundled_wallets_only,
                    mint_address=mint_address,
                    sell_percentage=sell_percentage,
                    slippage_bps=slippage_bps
                )
            else:
                raise Exception("No bundled wallets found in wallet data")
        
        elif operation == "sell_all":
            # Sell with all wallets (DevWallet + bundled)
            all_results = {}
            
            # First sell with DevWallet
            progress_data['current_step'] = 'Executing DevWallet sell...'
            progress_data['completed_operations'] = 0
            await query.edit_message_text(
                format_sell_operation_progress(progress_data),
                parse_mode=ParseMode.MARKDOWN
            )
            
            dev_wallets = [w for w in wallets_data if w['name'] == 'DevWallet']
            if dev_wallets:
                # Extract dev wallet credentials for PumpFun API
                dev_wallet = dev_wallets[0]
                dev_result = pumpfun_client.sell_dev_wallet(
                    dev_wallet_private_key=dev_wallet.get('privateKey'),
                    mint_address=mint_address,
                    sell_percentage=sell_percentage,
                    slippage_bps=slippage_bps
                )
                all_results['dev_wallet'] = dev_result
            
            # Then batch sell with bundled wallets
            progress_data['current_step'] = 'Executing batch sell...'
            progress_data['completed_operations'] = 1
            await query.edit_message_text(
                format_sell_operation_progress(progress_data),
                parse_mode=ParseMode.MARKDOWN
            )
            
            bundled_wallets_only = [w for w in wallets_data if w['name'] != 'DevWallet']
            if bundled_wallets_only:
                # Pass complete wallet objects to PumpFun API for correct naming
                batch_result = pumpfun_client.batch_sell_token(
                    wallets=bundled_wallets_only,
                    mint_address=mint_address,
                    sell_percentage=sell_percentage,
                    slippage_bps=slippage_bps
                )
                all_results['bundled_wallets'] = batch_result
            
            # Combine results for display
            results = {
                "message": "All wallets sell completed",
                "data": {
                    "status": "success",
                    "mintAddress": mint_address,
                    "sellPercentage": sell_percentage,
                    "operations": all_results
                }
            }
        
        # Show results
        logger.info(f"Preparing to show sell operation results: {results}")
        
        keyboard = [[build_button("« Back to Token Options", "back_to_token_options")]]
        
        try:
            # Handle the specific API response structure for sell operations
            if isinstance(results, dict) and "data" in results:
                api_data = results["data"]
                
                # Check if the operation was successful
                if api_data.get("success", False):
                    result_message = (
                        f"✅ **Sell Operation Completed Successfully!**\n\n"
                        f"Your tokens have been sold and confirmed on-chain.\n\n"
                        f"**Operation Summary:**\n"
                        f"• Token: `{mint_address[:8]}...{mint_address[-4:]}`\n"
                        f"• Percentage Sold: {sell_percentage}%\n"
                        f"• Operation Type: {operation.replace('_', ' ').title()}\n"
                        f"• Bundles Sent: {api_data.get('totalBundlesSent', 'N/A')}\n"
                        f"• Successful Bundles: {api_data.get('successfulBundles', 'N/A')}\n"
                        f"• Failed Bundles: {api_data.get('failedBundles', 0)}\n\n"
                    )
                    
                    # Add bundle details if available
                    bundle_results = api_data.get("bundleResults", [])
                    if bundle_results:
                        result_message += f"**Transaction Details:**\n"
                        for i, bundle in enumerate(bundle_results[:3]):  # Show max 3 bundles
                            if bundle.get("success"):
                                bundle_id = bundle.get("bundleId", "N/A")
                                result_message += f"• Bundle {i+1}: `{bundle_id[:8]}...{bundle_id[-8:]}`\n"
                                
                                # Add transaction count if available
                                transactions = bundle.get("transactions", [])
                                if transactions:
                                    result_message += f"  └ {len(transactions)} wallet(s) processed\n"
                        
                        if len(bundle_results) > 3:
                            result_message += f"• ... and {len(bundle_results) - 3} more bundle(s)\n"
                    
                    result_message += f"\n🎉 **Check your wallet balances to see the updated SOL amounts!**"
                    
                else:
                    # Handle failed operations
                    result_message = (
                        f"❌ **Sell Operation Failed**\n\n"
                        f"The sell operation was not successful.\n\n"
                        f"**Details:**\n"
                        f"• Token: `{mint_address[:8]}...{mint_address[-4:]}`\n"
                        f"• Attempted Percentage: {sell_percentage}%\n"
                        f"• Error: {api_data.get('message', 'Unknown error')}\n"
                    )
            else:
                # Fallback for unexpected response format
                logger.warning(f"Unexpected API response format: {results}")
                result_message = (
                    f"✅ **Sell Operation Completed**\n\n"
                    f"Your sell operation has been processed.\n\n"
                    f"**Operation Details:**\n"
                    f"• Token: `{mint_address[:8]}...{mint_address[-4:]}`\n"
                    f"• Percentage Sold: {sell_percentage}%\n"
                    f"• Operation Type: {operation.replace('_', ' ').title()}\n\n"
                    f"🎉 **Check your wallet balances to see the updated amounts!**"
                )
                
        except Exception as format_error:
            logger.error(f"Error formatting sell results: {str(format_error)}")
            logger.info(f"Full API response: {results}")
            
            # Simple fallback message
            result_message = (
                f"✅ **Sell Operation Completed**\n\n"
                f"Your sell operation has been executed.\n\n"
                f"**Operation Details:**\n"
                f"• Token: `{mint_address[:8]}...{mint_address[-4:]}`\n"
                f"• Percentage Sold: {sell_percentage}%\n"
                f"• Operation Type: {operation.replace('_', ' ').title()}\n\n"
                f"🎉 **Check your wallet balances to confirm the transaction!**"
            )
            
        await query.edit_message_text(
            result_message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.TOKEN_TRADING_OPERATION
        
    except Exception as e:
        logger.error(f"Error executing sell operation for user {user.id}: {str(e)}")
        
        keyboard = [[build_button("« Back to Token Options", "back_to_token_options")]]
        
        await query.edit_message_text(
            f"❌ **Sell Operation Failed**\n\n"
            f"An error occurred while executing the sell operation:\n\n"
            f"`{str(e)}`\n\n"
            f"**Common issues:**\n"
            f"• Insufficient SOL balance for transaction fees\n"
            f"• No tokens to sell in the specified wallets\n"
            f"• Network congestion or API timeout\n"
            f"• Invalid wallet credentials\n\n"
            f"Please check your wallet balances and try again.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.TOKEN_TRADING_OPERATION


async def show_airdrop_wallet_selection(update: Update, context: CallbackContext) -> int:
    """
    Show airdrop wallet selection for bundler management.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
    # Get user's bundled wallet records to find airdrop wallets
    user_bundled_wallets = bundled_wallet_storage.list_user_bundled_wallets(user.id)
    
    if not user_bundled_wallets:
        keyboard = [[build_button("« Back to Bundler Management", "back_to_bundler_mgmt")]]
        
        await query.edit_message_text(
            "📭 **No Airdrop Wallets Found**\n\n"
            "You haven't created any bundled wallets yet.\n\n"
            "Use 'Token Bundling (PumpFun)' to create your first token with bundled wallets!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLER_MANAGEMENT
    
    # Get unique airdrop wallets
    airdrop_wallets = {}
    for wallet_record in user_bundled_wallets:
        airdrop_address = wallet_record.get('airdrop_wallet_address')
        if airdrop_address and airdrop_address not in airdrop_wallets:
            airdrop_wallets[airdrop_address] = {
                'address': airdrop_address,
                'created_at': wallet_record.get('created_at', ''),
                'wallet_count': wallet_record.get('wallet_count', 0)
            }
    
    if not airdrop_wallets:
        keyboard = [[build_button("« Back to Bundler Management", "back_to_bundler_mgmt")]]
        
        await query.edit_message_text(
            "📭 **No Valid Airdrop Wallets Found**\n\n"
            "No airdrop wallet addresses found in your bundled wallet records.\n\n"
            "Please create new bundled wallets through the bundling system.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLER_MANAGEMENT
    
    # Build keyboard with airdrop wallet options
    keyboard = []
    for i, (address, wallet_info) in enumerate(list(airdrop_wallets.items())[:10]):
        display_address = f"{address[:8]}...{address[-4:]}"
        wallet_count = wallet_info.get('wallet_count', 0)
        keyboard.append([build_button(
            f"🎯 {display_address} ({wallet_count} wallets)", 
            f"{CallbackPrefix.AIRDROP_WALLET_SELECT}{i}"
        )])
    
    # Add navigation buttons
    keyboard.append([build_button("« Back to Bundler Management", "back_to_bundler_mgmt")])
    
    # Store airdrop wallets in session for later reference
    session_manager.update_session_value(user.id, "airdrop_wallets", list(airdrop_wallets.values()))
    
    message_text = "🎯 **Select Airdrop Wallet**\n\n"
    message_text += "Choose an airdrop wallet to view its bundled wallets and manage tokens:\n\n"
    
    for address, wallet_info in airdrop_wallets.items():
        display_address = f"{address[:8]}...{address[-4:]}"
        wallet_count = wallet_info.get('wallet_count', 0)
        created_at = wallet_info.get('created_at', 'Unknown')
        message_text += f"🎯 **{display_address}**\n"
        message_text += f"   └ {wallet_count} bundled wallets\n"
        message_text += f"   └ Created: {created_at[:10] if created_at else 'Unknown'}\n\n"
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.AIRDROP_WALLET_SELECTION


async def airdrop_wallet_selection_choice(update: Update, context: CallbackContext) -> int:
    """
    Handle airdrop wallet selection and show wallet balances.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    
    if choice == "back_to_bundler_mgmt":
        from .start_handler import bundler_management
        return await bundler_management(update, context)
    
    # Handle airdrop wallet selection
    if choice.startswith(CallbackPrefix.AIRDROP_WALLET_SELECT):
        try:
            # Extract wallet index from callback data
            wallet_index = int(choice.replace(CallbackPrefix.AIRDROP_WALLET_SELECT, ""))
            
            # Get stored airdrop wallets from session
            airdrop_wallets = session_manager.get_session_value(user.id, "airdrop_wallets", [])
            
            if 0 <= wallet_index < len(airdrop_wallets):
                selected_airdrop_wallet = airdrop_wallets[wallet_index]
                
                # Store selected airdrop wallet in session
                session_manager.update_session_value(user.id, "selected_airdrop_wallet", selected_airdrop_wallet)
                
                return await show_wallet_balance_overview(update, context, selected_airdrop_wallet)
            else:
                logger.error(f"Invalid airdrop wallet index: {wallet_index}")
                
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing airdrop wallet selection: {str(e)}")
    
    return ConversationState.AIRDROP_WALLET_SELECTION


async def show_wallet_balance_overview(update: Update, context: CallbackContext, airdrop_wallet: Dict[str, Any]) -> int:
    """
    Show balance overview for selected airdrop wallet and its bundled wallets.
    
    Args:
        update: The update object
        context: The context object
        airdrop_wallet: Selected airdrop wallet information
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
    try:
        airdrop_address = airdrop_wallet['address']
        
        # Show loading message
        await query.edit_message_text(
            f"🔍 **Checking Wallet Balances**\n\n"
            f"Loading balance information for airdrop wallet:\n"
            f"`{airdrop_address[:8]}...{airdrop_address[-4:]}`\n\n"
            f"⏳ Please wait...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Load bundled wallets
        bundled_wallets = bundled_wallet_storage.load_bundled_wallets(airdrop_address, user.id)
        
        if not bundled_wallets:
            keyboard = [[build_button("« Back to Airdrop Selection", "back_to_airdrop_selection")]]
            
            await query.edit_message_text(
                f"❌ **No Bundled Wallets Found**\n\n"
                f"No bundled wallets found for airdrop wallet:\n"
                f"`{airdrop_address[:8]}...{airdrop_address[-4:]}`\n\n"
                f"Please create bundled wallets through the bundling system.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.WALLET_BALANCE_OVERVIEW
        
        # Initialize PumpFun client for balance checking
        pumpfun_client = PumpFunClient()
        
        # Check balances for all wallets
        wallet_balances = []
        dev_wallet_balance = None
        
        for wallet in bundled_wallets:
            wallet_address = wallet.get('address') or wallet.get('public_key')
            wallet_name = wallet.get('name', 'Unknown')
            
            if wallet_address:
                try:
                    # Get SOL balance using the working legacy endpoint
                    balance_response = pumpfun_client.get_wallet_balance(wallet_address)
                    
                    # Parse balance from response (handles both enhanced and legacy formats)
                    sol_balance = 0.0
                    if balance_response and 'data' in balance_response:
                        data = balance_response['data']
                        sol_balance = data.get('balance', 0.0)
                    
                    # Try to get complete balance (SOL + SPL tokens) if available
                    token_info = []
                    try:
                        complete_balance = pumpfun_client.get_wallet_complete_balance(wallet_address)
                        if complete_balance and 'data' in complete_balance:
                            complete_data = complete_balance['data']
                            tokens = complete_data.get('tokens', [])
                            for token in tokens:
                                if token.get('balance', 0) > 0:  # Only include tokens with positive balance
                                    token_info.append({
                                        'mint': token.get('mint'),
                                        'balance': token.get('balance', 0),
                                        'uiAmount': token.get('uiAmount', 0.0),
                                        'decimals': token.get('decimals', 6),
                                        'symbol': token.get('symbol')
                                    })
                    except Exception as token_error:
                        logger.warning(f"Could not fetch SPL tokens for {wallet_name}: {str(token_error)}")
                    
                    logger.info(f"Balance check for {wallet_name} ({wallet_address[:8]}...{wallet_address[-4:]}): {sol_balance} SOL, {len(token_info)} SPL tokens")
                    
                    wallet_info = {
                        'name': wallet_name,
                        'address': wallet_address,
                        'sol_balance': sol_balance,
                        'spl_tokens': token_info,
                        'token_count': len(token_info),
                        'is_dev_wallet': wallet_name == 'DevWallet'
                    }
                    
                    wallet_balances.append(wallet_info)
                    
                    if wallet_name == 'DevWallet':
                        dev_wallet_balance = sol_balance
                        
                except Exception as e:
                    logger.error(f"Error checking balance for wallet {wallet_name}: {str(e)}")
                    wallet_balances.append({
                        'name': wallet_name,
                        'address': wallet_address,
                        'sol_balance': 0.0,
                        'spl_tokens': [],
                        'token_count': 0,
                        'error': str(e),
                        'is_dev_wallet': wallet_name == 'DevWallet'
                    })
        
        # Store wallet information in session
        session_manager.update_session_value(user.id, "wallet_balances", wallet_balances)
        
        # Build balance overview message
        message_text = f"💰 **Wallet Balance Overview**\n\n"
        message_text += f"**Airdrop Wallet:** `{airdrop_address[:8]}...{airdrop_address[-4:]}`\n\n"
        
        # Show DevWallet first
        dev_wallets = [w for w in wallet_balances if w['is_dev_wallet']]
        if dev_wallets:
            dev_wallet = dev_wallets[0]
            message_text += f"🏆 **DevWallet**\n"
            message_text += f"   └ Address: `{dev_wallet['address'][:8]}...{dev_wallet['address'][-4:]}`\n"
            message_text += f"   └ SOL Balance: **{dev_wallet['sol_balance']:.6f} SOL**\n"
            
            # Show SPL tokens if any
            spl_tokens = dev_wallet.get('spl_tokens', [])
            if spl_tokens:
                message_text += f"   └ SPL Tokens: **{len(spl_tokens)} token(s)**\n"
                for token in spl_tokens[:3]:  # Show first 3 tokens
                    symbol = token.get('symbol') or f"{token.get('mint', '')[:8]}..."
                    ui_amount = token.get('uiAmount', 0.0)
                    message_text += f"     • {symbol}: {ui_amount:.4f}\n"
                if len(spl_tokens) > 3:
                    message_text += f"     • ... and {len(spl_tokens) - 3} more\n"
            
            if dev_wallet.get('error'):
                message_text += f"   └ ⚠️ Error: {dev_wallet['error']}\n"
            message_text += "\n"
        
        # Show bundled wallets
        bundled_only = [w for w in wallet_balances if not w['is_dev_wallet']]
        if bundled_only:
            message_text += f"🎯 **Bundled Wallets ({len(bundled_only)})**\n"
            total_bundled_balance = 0.0
            total_bundled_tokens = 0
            
            for wallet in bundled_only[:5]:  # Show first 5 bundled wallets
                token_count = wallet.get('token_count', 0)
                total_bundled_tokens += token_count
                message_text += f"   └ {wallet['name']}: **{wallet['sol_balance']:.6f} SOL**"
                if token_count > 0:
                    message_text += f" + {token_count} tokens"
                message_text += "\n"
                total_bundled_balance += wallet['sol_balance']
            
            if len(bundled_only) > 5:
                remaining_wallets = bundled_only[5:]
                remaining_balance = sum(w['sol_balance'] for w in remaining_wallets)
                remaining_tokens = sum(w.get('token_count', 0) for w in remaining_wallets)
                total_bundled_balance += remaining_balance
                total_bundled_tokens += remaining_tokens
                message_text += f"   └ ... and {len(remaining_wallets)} more wallets\n"
            
            message_text += f"\n**Total Bundled Balance:** {total_bundled_balance:.6f} SOL"
            if total_bundled_tokens > 0:
                message_text += f" + {total_bundled_tokens} SPL tokens"
            message_text += "\n\n"
        
        # Add trading readiness assessment
        min_sol_for_trading = 0.001  # Minimum SOL needed per wallet for trading
        
        if dev_wallet_balance is not None and dev_wallet_balance >= min_sol_for_trading:
            message_text += "✅ **DevWallet Ready for Trading**\n"
        else:
            message_text += "❌ **DevWallet Needs Funding** (min 0.001 SOL)\n"
        
        tradeable_bundled = len([w for w in bundled_only if w['sol_balance'] >= min_sol_for_trading])
        message_text += f"🎯 **{tradeable_bundled}/{len(bundled_only)} Bundled Wallets Ready**\n\n"
        
        # Build keyboard
        keyboard = [
            [build_button("🪙 View Tokens for Trading", f"{CallbackPrefix.WALLET_BALANCE_VIEW}view_tokens")],
            [build_button("🔄 Refresh Balances", f"{CallbackPrefix.WALLET_BALANCE_VIEW}refresh")],
            [build_button("« Back to Airdrop Selection", "back_to_airdrop_selection")]
        ]
        
        await query.edit_message_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_BALANCE_OVERVIEW
        
    except Exception as e:
        logger.error(f"Error showing wallet balance overview: {str(e)}")
        
        keyboard = [[build_button("« Back to Airdrop Selection", "back_to_airdrop_selection")]]
        
        await query.edit_message_text(
            f"❌ **Error Loading Wallet Balances**\n\n"
            f"An error occurred while checking wallet balances:\n\n"
            f"`{str(e)}`\n\n"
            f"Please try again or select a different airdrop wallet.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_BALANCE_OVERVIEW


async def wallet_balance_overview_choice(update: Update, context: CallbackContext) -> int:
    """
    Handle wallet balance overview choices.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    
    if choice == "back_to_airdrop_selection":
        return await show_airdrop_wallet_selection(update, context)
    
    # Handle balance overview actions
    if choice.startswith(CallbackPrefix.WALLET_BALANCE_VIEW):
        action = choice.replace(CallbackPrefix.WALLET_BALANCE_VIEW, "")
        
        if action == "view_tokens":
            return await show_token_list(update, context)
        elif action == "refresh":
            # Refresh balances by re-showing the overview
            selected_airdrop_wallet = session_manager.get_session_value(user.id, "selected_airdrop_wallet")
            if selected_airdrop_wallet:
                return await show_wallet_balance_overview(update, context, selected_airdrop_wallet)
    
    return ConversationState.WALLET_BALANCE_OVERVIEW


async def back_to_token_options(update: Update, context: CallbackContext) -> int:
    """
    Handle back to token options navigation.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Get selected token from session and return to its management options
    selected_token = session_manager.get_session_value(user.id, "selected_token")
    if selected_token:
        return await show_token_management_options(update, context, selected_token)
    else:
        return await show_token_list(update, context)
