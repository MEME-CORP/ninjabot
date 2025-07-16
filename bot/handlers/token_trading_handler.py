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
        return await show_token_list(update, context)
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
        keyboard = [[build_button("« Back to Bundler Management", "back_to_bundler_mgmt")]]
        
        await query.edit_message_text(
            "📭 **No Tokens Found**\n\n"
            "You haven't created any tokens yet.\n\n"
            "Use 'Token Bundling (PumpFun)' to create your first token!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLER_MANAGEMENT
    
    # Build keyboard with token options (max 10 tokens)
    keyboard = []
    for i, token in enumerate(user_tokens[:10]):
        token_name = token.get('token_name', f'Token {i+1}')
        # Truncate long names for button display
        display_name = token_name[:25] + "..." if len(token_name) > 25 else token_name
        keyboard.append([build_button(f"🪙 {display_name}", f"{CallbackPrefix.TOKEN_SELECT}{i}")])
    
    # Add navigation buttons
    keyboard.append([build_button("« Back to Bundler Management", "back_to_bundler_mgmt")])
    
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
        # Go back to bundler management
        from .start_handler import start_bundler_management_workflow
        return await start_bundler_management_workflow(update, context)
    
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
        
        # Get wallet data from session (should have been stored during token creation)
        session_data = session_manager.get_session_data(user.id)
        airdrop_wallet = session_data.get('airdrop_wallet')
        
        # Try to get wallets from storage
        wallets_data = None
        if airdrop_wallet and 'address' in airdrop_wallet:
            airdrop_address = airdrop_wallet['address']
            
            # Load bundled wallets from storage
            bundled_wallets = bundled_wallet_storage.load_bundled_wallets(airdrop_address, user.id)
            
            if bundled_wallets:
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
                
                # Add bundled wallets (if needed for the operation)
                if operation in ["sell_bundled", "sell_all"]:
                    for wallet in bundled_wallets:
                        if wallet.get('name') != 'DevWallet' and 'private_key' in wallet:
                            wallets_data.append({
                                "name": wallet['name'],
                                "privateKey": wallet['private_key']
                            })
        
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
        
        if operation == "sell_dev":
            # Sell with DevWallet only
            progress_data['current_step'] = 'Executing DevWallet sell...'
            await query.edit_message_text(
                format_sell_operation_progress(progress_data),
                parse_mode=ParseMode.MARKDOWN
            )
            
            dev_wallets = [w for w in wallets_data if w['name'] == 'DevWallet']
            if dev_wallets:
                results = api_client.sell_token_dev_wallet(
                    mint_address=mint_address,
                    sell_percentage=sell_percentage,
                    slippage_bps=slippage_bps,
                    wallets=dev_wallets
                )
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
                results = api_client.batch_sell_tokens(
                    mint_address=mint_address,
                    sell_percentage=sell_percentage,
                    slippage_bps=slippage_bps,
                    wallets=bundled_wallets_only
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
                dev_result = api_client.sell_token_dev_wallet(
                    mint_address=mint_address,
                    sell_percentage=sell_percentage,
                    slippage_bps=slippage_bps,
                    wallets=dev_wallets
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
                batch_result = api_client.batch_sell_tokens(
                    mint_address=mint_address,
                    sell_percentage=sell_percentage,
                    slippage_bps=slippage_bps,
                    wallets=bundled_wallets_only
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
        keyboard = [[build_button("« Back to Token Options", "back_to_token_options")]]
        
        await query.edit_message_text(
            format_sell_operation_results(results),
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


async def back_to_token_options(update: Update, context: CallbackContext) -> int:
    """
    Go back to token management options.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Get selected token from session
    selected_token = session_manager.get_session_value(user.id, "selected_token")
    
    if selected_token:
        return await show_token_management_options(update, context, selected_token)
    else:
        return await show_token_list(update, context)


logger.info("Token trading handler loaded with post-creation trading operations")
