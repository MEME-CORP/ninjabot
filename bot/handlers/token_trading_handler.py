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


def get_latest_token_mint_address(user_id: int) -> Optional[str]:
    """
    Get the mint address of the most recently created token for a user.
    
    Args:
        user_id: User ID to get tokens for
        
    Returns:
        Mint address of the latest token, or None if no tokens found
    """
    try:
        user_tokens = token_storage.get_user_tokens(user_id)
        if not user_tokens:
            logger.info(f"No tokens found for user {user_id}")
            return None
        
        # Sort tokens by created_at timestamp (most recent first)
        sorted_tokens = sorted(
            user_tokens, 
            key=lambda x: x.get('created_at', ''), 
            reverse=True
        )
        
        latest_token = sorted_tokens[0]
        mint_address = latest_token.get('mint_address')
        token_name = latest_token.get('token_name', 'Unknown')
        
        logger.info(f"Latest token for user {user_id}: {token_name} ({mint_address})")
        return mint_address
        
    except Exception as e:
        logger.error(f"Failed to get latest token for user {user_id}: {e}")
        return None


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
        # Go back to wallet overview (no balance checking)
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
    
    # Handle trading operations (support both old and new callback patterns)
    if choice.startswith(CallbackPrefix.TOKEN_OPERATION) or choice.startswith("token_operation_"):
        if choice.startswith(CallbackPrefix.TOKEN_OPERATION):
            operation = choice.replace(CallbackPrefix.TOKEN_OPERATION, "")
        else:
            operation = choice.replace("token_operation_", "")
        
        # Get selected token from session
        selected_token = session_manager.get_session_value(user.id, "selected_token")
        logger.info(f"Token operation {operation} selected for token: {selected_token.get('token_name', 'Unknown') if selected_token else 'None'}")
        
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
    
    # Refresh session before potentially long sell operation
    session_manager.refresh_session(user.id)
    
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
            # Refresh session before accessing session data to prevent expiration issues
            session_manager.refresh_session(user.id)
            session_data = session_manager.get_session_data(user.id)
            if session_data:  # Check if session_data is not None
                airdrop_wallet = session_data.get('airdrop_wallet')
                if airdrop_wallet and 'address' in airdrop_wallet:
                    airdrop_address = airdrop_wallet['address']
                    logger.info(f"Found airdrop wallet in session: {airdrop_address[:8]}...")
            else:
                logger.warning(f"Session data is None for user {user.id}, session may have expired")
        
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
            # Sell with DevWallet only - SIMPLIFIED PROCESS
            progress_data['current_step'] = 'Executing DevWallet sell...'
            await query.edit_message_text(
                format_sell_operation_progress(progress_data),
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Filter for DevWallet only
            dev_wallets = [w for w in wallets_data if w['name'] == 'DevWallet']
            if not dev_wallets:
                raise Exception("DevWallet not found in wallet data")
            
            logger.info(f"Starting simplified DevWallet sell for mint {mint_address} with {sell_percentage}% of tokens")
            
            # ✅ SIMPLIFIED API CALL - API handles balance validation internally
            results = pumpfun_client.sell_dev_wallet(
                mint_address=mint_address,
                sell_percentage=sell_percentage,
                slippage_bps=slippage_bps,
                wallets=dev_wallets  # Pass wallet objects directly
            )
            
            logger.info(f"DevWallet sell completed: {results}")
        
        elif operation == "sell_bundled":
            # Sell with bundled wallets only - SIMPLIFIED PROCESS
            progress_data['current_step'] = 'Executing batch sell...'
            await query.edit_message_text(
                format_sell_operation_progress(progress_data),
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Filter non-DevWallets (server excludes DevWallet anyway)
            bundled_wallets_only = [w for w in wallets_data if w['name'] != 'DevWallet']
            if not bundled_wallets_only:
                raise Exception("No bundled wallets found in wallet data")
            
            logger.info(f"Starting simplified batch sell for mint {mint_address} with {sell_percentage}% of tokens")
            
            # ✅ SIMPLIFIED API CALL - API handles balance validation internally
            results = pumpfun_client.batch_sell_token(
                mint_address=mint_address,
                sell_percentage=sell_percentage,
                slippage_bps=slippage_bps,
                wallets=bundled_wallets_only
            )
        
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
                # ✅ SIMPLIFIED API CALL for DevWallet - API validates internally
                dev_result = pumpfun_client.sell_dev_wallet(
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
                # ✅ SIMPLIFIED API CALL for batch sell - API validates internally
                batch_result = pumpfun_client.batch_sell_token(
                    mint_address=mint_address,
                    sell_percentage=sell_percentage,
                    slippage_bps=slippage_bps,
                    wallets=bundled_wallets_only
                )
                all_results['bundled_wallets'] = batch_result
            
            # Combine results for display
            # Determine overall success from sub-operation results
            def _op_success(res):
                try:
                    if isinstance(res, dict) and isinstance(res.get("data"), dict):
                        d = res["data"]
                        if d.get("success"):
                            return True
                        if d.get("successfulBundles", 0) > 0:
                            return True
                        br = d.get("bundleResults") or []
                        if isinstance(br, list) and any(isinstance(item, dict) and item.get("success") for item in br):
                            return True
                except Exception:
                    pass
                return False

            op_values = [v for v in all_results.values() if v is not None]
            overall_success = any(_op_success(v) for v in op_values) if op_values else False

            results = {
                "message": "All wallets sell completed",
                "data": {
                    "success": overall_success,
                    "status": "success" if overall_success else "failed",
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
                
                # Enhanced success detection - check multiple indicators like in PumpFun client
                def _is_sell_successful(data):
                    """Check multiple success indicators from API response."""
                    if data.get("success"):
                        return True
                    if data.get("successfulBundles", 0) > 0:
                        return True
                    bundle_results = data.get("bundleResults", [])
                    if isinstance(bundle_results, list) and any(
                        isinstance(item, dict) and item.get("success") for item in bundle_results
                    ):
                        return True
                    return False
                
                # Check if the operation was successful using enhanced detection
                if _is_sell_successful(api_data):
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
                    
                    result_message += f"\n🎉 **Transaction completed! Check your wallets to see updated amounts!**\n\n"
                    result_message += f"**Please note that it may take some time for the transaction to be fully processed.**"
                    
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
                    f"🎉 **Transaction completed! Check your wallets to see updated amounts!**"
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
                f"🎉 **Transaction submitted! Check your wallets to confirm completion!**"
            )
            
        await query.edit_message_text(
            result_message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Refresh session after sell operation completes
        session_manager.refresh_session(user.id)
        
        return ConversationState.TOKEN_TRADING_OPERATION
        
    except Exception as e:
        logger.error(f"Error executing sell operation for user {user.id}: {str(e)}")
        
        keyboard = [[build_button("« Back to Token Options", "back_to_token_options")]]
        
        await query.edit_message_text(
            f"❌ **Sell Operation Failed**\n\n"
            f"An error occurred while executing the sell operation:\n\n"
            f"`{str(e)}`\n\n"
            f"**Common issues:**\n"
            f"• Insufficient funds (validated by API)\n"
            f"• No tokens to sell in the specified wallets\n"
            f"• Network congestion or API timeout\n"
            f"• Invalid wallet credentials\n\n"
            f"The API validates all balances automatically. Please try again.",
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
                
                # Check if there's a pending sell operation from bundler management
                pending_operation = session_manager.get_session_value(user.id, "token_operation")
                selected_token = session_manager.get_session_value(user.id, "selected_token")
                
                logger.info(f"DEBUG: Airdrop wallet selected - pending_operation: {pending_operation}, selected_token exists: {bool(selected_token)}")
                
                if pending_operation and pending_operation.startswith("sell_") and selected_token:
                    # ✅ BYPASS BALANCE CHECKING - API handles validation internally
                    logger.info(f"⚡ Direct sell flow (no balance checking): {pending_operation}")
                    from .bundler_management_handler import show_bundler_sell_percentage_selection
                    return await show_bundler_sell_percentage_selection(update, context, selected_token, pending_operation)
                
                return await show_wallet_balance_overview(update, context, selected_airdrop_wallet)
            else:
                logger.error(f"Invalid airdrop wallet index: {wallet_index}")
                
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing airdrop wallet selection: {str(e)}")
    
    return ConversationState.AIRDROP_WALLET_SELECTION


async def show_wallet_balance_overview(update: Update, context: CallbackContext, airdrop_wallet: Dict[str, Any]) -> int:
    """
    Show wallet overview WITHOUT balance checking - API handles validation internally.
    
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
        
        logger.info(f"✅ Loading wallet overview for {airdrop_address[:8]}...{airdrop_address[-4:]} - NO BALANCE CHECKING")
        
        # Load bundled wallets - NO BALANCE CALLS
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
        
        # Build wallet summary WITHOUT balance checking
        dev_wallet_count = len([w for w in bundled_wallets if w.get('name') == 'DevWallet'])
        bundled_wallet_count = len([w for w in bundled_wallets if w.get('name') != 'DevWallet'])
        
        logger.info(f"📊 Wallet summary: {dev_wallet_count} DevWallet, {bundled_wallet_count} bundled wallets")
        
        # Build overview message - NO BALANCE DATA
        message_text = f"🎯 **Wallet Overview**\n\n"
        message_text += f"**Airdrop Wallet:** `{airdrop_address[:8]}...{airdrop_address[-4:]}`\n\n"
        message_text += f"📁 **Wallet Summary:**\n"
        message_text += f"   └ DevWallet: {dev_wallet_count} wallet(s)\n"
        message_text += f"   └ Bundled Wallets: {bundled_wallet_count} wallet(s)\n"
        message_text += f"   └ Total Wallets: {len(bundled_wallets)}\n\n"
        
        message_text += f"⚡ **Ready for Trading**\n"
        message_text += f"All wallet credentials loaded and ready for API operations.\n"
        message_text += f"Balance validation will be handled by the API during trading.\n\n"
        
        message_text += f"💡 **Next Steps:**\n"
        message_text += f"• Select 'View Tokens' to start trading operations\n"
        message_text += f"• API will validate balances automatically during transactions\n"
        message_text += f"• No pre-validation delays or session timeouts\n"
        
        # Build keyboard
        keyboard = [
            [build_button("🪙 View Tokens for Trading", f"{CallbackPrefix.WALLET_BALANCE_VIEW}view_tokens")],
            [build_button("« Back to Airdrop Selection", "back_to_airdrop_selection")]
        ]
        
        await query.edit_message_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_BALANCE_OVERVIEW
        
    except Exception as e:
        logger.error(f"❌ Error loading wallet overview: {str(e)}")
        
        keyboard = [[build_button("« Back to Airdrop Selection", "back_to_airdrop_selection")]]
        
        await query.edit_message_text(
            f"❌ **Error Loading Wallet Overview**\n\n"
            f"An error occurred while loading wallet information:\n\n"
            f"`{str(e)}`\n\n"
            f"Please try again or select a different airdrop wallet.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_BALANCE_OVERVIEW


async def wallet_balance_overview_choice(update: Update, context: CallbackContext) -> int:
    """
    Handle wallet overview choices - NO BALANCE OPERATIONS.
    
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
    
    # Handle overview actions
    if choice.startswith(CallbackPrefix.WALLET_BALANCE_VIEW):
        action = choice.replace(CallbackPrefix.WALLET_BALANCE_VIEW, "")
        
        if action == "view_tokens":
            logger.info(f"🪙 User {user.id} navigating to token list - NO BALANCE CHECKING")
            return await show_token_list(update, context)
    
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
