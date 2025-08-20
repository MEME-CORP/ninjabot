"""
Bundler Management Handler

This module handles token management operations for created PumpFun tokens.
It provides functionality to view, buy, and sell tokens with dev and bundled wallets.

Architecture:
- Minimal integration with existing bundling workflow
- Preserves existing working code structure
- Uses existing token storage and session management
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
    format_token_management_options_message
)
from bot.state.session_manager import session_manager
from bot.utils.token_storage import token_storage


async def bundler_management_choice(update: Update, context: CallbackContext) -> int:
    """
    Handle bundler management choice - NEW WALLET-FIRST APPROACH.
    
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
        # NEW: Start with airdrop wallet selection instead of token list
        return await show_airdrop_wallet_selection_for_selling(update, context)
    elif choice == "back_to_activities":
        # Go back to activity selection by redirecting
        from bot.utils.message_utils import format_activity_selection_message
        
        keyboard = [
            [build_button("📊 Volume Generation", f"{CallbackPrefix.ACTIVITY}{CallbackPrefix.VOLUME_GENERATION}")],
            [build_button("🚀 Token Bundling (PumpFun)", f"{CallbackPrefix.ACTIVITY}{CallbackPrefix.BUNDLING}")],
            [build_button("🎛️ Bundler Management", f"{CallbackPrefix.ACTIVITY}{CallbackPrefix.BUNDLER_MANAGEMENT}")]
        ]
        
        await query.edit_message_text(
            format_activity_selection_message(),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.ACTIVITY_SELECTION
    else:
        logger.warning(f"Unknown bundler management choice: {choice} from user {user.id}")
        return ConversationState.BUNDLER_MANAGEMENT


async def show_airdrop_wallet_selection_for_selling(update: Update, context: CallbackContext) -> int:
    """
    Show airdrop wallet selection for token selling - NO BALANCE CHECKING.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
    # Import bundled wallet storage
    from bot.utils.wallet_storage import bundled_wallet_storage
    
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
            f"airdrop_select_{i}"
        )])
    
    # Add navigation buttons
    keyboard.append([build_button("« Back to Bundler Management", "back_to_bundler_mgmt")])
    
    # Store airdrop wallets in session for later reference
    session_manager.update_session_value(user.id, "selling_airdrop_wallets", list(airdrop_wallets.values()))
    
    message_text = "🎯 **Select Airdrop Wallet for Token Selling**\n\n"
    message_text += "Choose an airdrop wallet to load its child wallets and proceed to token selling:\n\n"
    
    for address, wallet_info in airdrop_wallets.items():
        display_address = f"{address[:8]}...{address[-4:]}"
        wallet_count = wallet_info.get('wallet_count', 0)
        created_at = wallet_info.get('created_at', 'Unknown')
        message_text += f"🎯 **{display_address}**\n"
        message_text += f"   └ {wallet_count} bundled wallets\n"
        message_text += f"   └ Created: {created_at[:10] if created_at else 'Unknown'}\n\n"
    
    message_text += "⚡ **No Balance Checking** - Direct to sell menu after wallet selection!"
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.SELLING_AIRDROP_SELECTION


async def handle_airdrop_wallet_selection_for_selling(update: Update, context: CallbackContext) -> int:
    """
    Handle airdrop wallet selection and load child wallets - NO BALANCE CHECKING.
    
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
        return await start_bundler_management_workflow(update, context)
    
    # Extract airdrop wallet index from callback data
    if choice.startswith("airdrop_select_"):
        try:
            wallet_index = int(choice.replace("airdrop_select_", ""))
            
            # Get airdrop wallets from session
            airdrop_wallets = session_manager.get_session_value(user.id, "selling_airdrop_wallets", [])
            
            if 0 <= wallet_index < len(airdrop_wallets):
                selected_airdrop_wallet = airdrop_wallets[wallet_index]
                airdrop_address = selected_airdrop_wallet['address']
                
                # Store selected airdrop wallet in session
                session_manager.update_session_value(user.id, "selected_selling_airdrop_wallet", selected_airdrop_wallet)
                
                # Load bundled wallets for this airdrop wallet
                from bot.utils.wallet_storage import bundled_wallet_storage
                
                logger.info(f"Loading child wallets for airdrop wallet {airdrop_address} - NO BALANCE CHECKING")
                bundled_wallets = bundled_wallet_storage.load_bundled_wallets(airdrop_address, user.id)
                
                if not bundled_wallets:
                    keyboard = [[build_button("« Back to Airdrop Selection", "back_to_airdrop_selection")]]
                    
                    await query.edit_message_text(
                        f"❌ **No Child Wallets Found**\n\n"
                        f"No bundled wallets found for airdrop wallet:\n"
                        f"`{airdrop_address[:8]}...{airdrop_address[-4:]}`\n\n"
                        f"Please create bundled wallets through the bundling system.",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    return ConversationState.SELLING_AIRDROP_SELECTION
                
                logger.info(f"Successfully loaded {len(bundled_wallets)} child wallets for airdrop wallet {airdrop_address}")
                
                # Store child wallets in session
                session_manager.update_session_value(user.id, "loaded_child_wallets", bundled_wallets)
                
                # Get user's created tokens to show available tokens for selling
                user_tokens = token_storage.get_user_tokens(user.id)
                
                if not user_tokens:
                    keyboard = [[build_button("« Back to Airdrop Selection", "back_to_airdrop_selection")]]
                    
                    await query.edit_message_text(
                        "📭 **No Tokens Found**\n\n"
                        "You haven't created any tokens yet.\n\n"
                        "Use 'Token Bundling (PumpFun)' to create your first token!",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    return ConversationState.SELLING_AIRDROP_SELECTION
                
                # Show token selection for selling with this wallet setup
                return await show_tokens_for_selling(update, context, selected_airdrop_wallet, bundled_wallets, user_tokens)
                
            else:
                logger.error(f"Invalid airdrop wallet index: {wallet_index}")
                return ConversationState.SELLING_AIRDROP_SELECTION
                
        except ValueError:
            logger.error(f"Invalid airdrop wallet selection format: {choice}")
            return ConversationState.SELLING_AIRDROP_SELECTION
    
    return ConversationState.SELLING_AIRDROP_SELECTION


async def show_tokens_for_selling(update: Update, context: CallbackContext, airdrop_wallet: Dict[str, Any], child_wallets: List[Dict[str, Any]], user_tokens: List[Dict[str, Any]]) -> int:
    """
    Show available tokens for selling with loaded wallet setup - NO BALANCE CHECKING.
    
    Args:
        update: The update object
        context: The context object
        airdrop_wallet: Selected airdrop wallet
        child_wallets: Loaded child wallets
        user_tokens: User's created tokens
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
    # Build keyboard with token options
    keyboard = []
    for i, token in enumerate(user_tokens[:10]):
        token_name = token.get('token_name', f'Token {i+1}')
        display_name = token_name[:25] + "..." if len(token_name) > 25 else token_name
        keyboard.append([build_button(f"🪙 {display_name}", f"sell_token_{i}")])
    
    # Add navigation buttons
    keyboard.append([build_button("« Back to Airdrop Selection", "back_to_airdrop_selection")])
    
    # Store tokens in session
    session_manager.update_session_value(user.id, "selling_tokens", user_tokens)
    
    airdrop_address = airdrop_wallet['address']
    child_count = len(child_wallets)
    
    message_text = f"🪙 **Select Token to Sell**\n\n"
    message_text += f"**Airdrop Wallet:** `{airdrop_address[:8]}...{airdrop_address[-4:]}`\n"
    message_text += f"**Child Wallets Loaded:** {child_count} wallets\n\n"
    message_text += f"Choose a token to proceed to the sell menu:\n\n"
    
    for i, token in enumerate(user_tokens[:5]):  # Show first 5 tokens in description
        token_name = token.get('token_name', f'Token {i+1}')
        mint_address = token.get('mint_address', 'Unknown')
        message_text += f"🪙 **{token_name}**\n"
        message_text += f"   └ Mint: `{mint_address[:8]}...{mint_address[-4:]}`\n\n"
    
    if len(user_tokens) > 5:
        message_text += f"... and {len(user_tokens) - 5} more tokens\n\n"
    
    message_text += f"⚡ **Ready for Direct Selling** - No balance checks!"
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.SELLING_TOKEN_SELECTION


async def handle_token_selection_for_selling(update: Update, context: CallbackContext) -> int:
    """
    Handle token selection and redirect to existing sell menu - NO BALANCE CHECKING.
    
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
        return await show_airdrop_wallet_selection_for_selling(update, context)
    
    # Extract token index from callback data
    if choice.startswith("sell_token_"):
        try:
            token_index = int(choice.replace("sell_token_", ""))
            
            # Get tokens from session
            selling_tokens = session_manager.get_session_value(user.id, "selling_tokens", [])
            
            if 0 <= token_index < len(selling_tokens):
                selected_token = selling_tokens[token_index]
                
                # Store selected token in session
                session_manager.update_session_value(user.id, "selected_token", selected_token)
                
                # Set sell operation for bundled wallets (since we loaded child wallets)
                session_manager.update_session_value(user.id, "token_operation", "sell_bundled")
                
                logger.info(f"Token selected for selling: {selected_token.get('token_name', 'Unknown')} - redirecting to existing sell menu")
                
                # Redirect to existing sell percentage selection (reuse existing functionality)
                return await show_bundler_sell_percentage_selection(update, context, selected_token, "sell_bundled")
                
            else:
                logger.error(f"Invalid token index {token_index} for user {user.id}")
                return ConversationState.SELLING_TOKEN_SELECTION
                
        except ValueError:
            logger.error(f"Invalid token selection format: {choice} from user {user.id}")
            return ConversationState.SELLING_TOKEN_SELECTION
    
    return ConversationState.SELLING_TOKEN_SELECTION


async def show_bundler_sell_percentage_selection(update: Update, context: CallbackContext, token_data: Dict[str, Any], operation: str) -> int:
    """
    Show sell percentage selection for bundler operations - NO BALANCE CHECKING.
    
    Args:
        update: The update object
        context: The context object 
        token_data: Selected token data
        operation: The sell operation type
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
    # Store token and operation data
    session_manager.update_session_value(user.id, "selected_token", token_data)
    session_manager.update_session_value(user.id, "token_operation", operation)
    
    token_name = token_data.get('token_name', 'Unknown Token')
    mint_address = token_data.get('mint_address', 'Unknown Address')
    
    operation_text = {
        "sell_dev": "🔴 **Sell from Dev Wallet**",
        "sell_bundled": "🔴 **Sell from Bundled Wallets**", 
        "sell_all": "🔴 **Sell from All Wallets**"
    }.get(operation, "Unknown Operation")
    
    # Percentage options
    keyboard = [
        [
            build_button("25%", "bundler_sell_25"),
            build_button("50%", "bundler_sell_50"),
            build_button("75%", "bundler_sell_75")
        ],
        [build_button("100%", "bundler_sell_100")],
        [build_button("« Back to Token Options", "back_to_token_options")]
    ]
    
    await query.edit_message_text(
        f"{operation_text}\n\n"
        f"**Token:** {token_name}\n"
        f"**Mint:** `{mint_address}`\n\n"
        f"💡 **Select Sell Percentage**\n\n"
        f"Choose what percentage of tokens to sell:\n\n"
        f"⚠️ **Note:** No balance checking will be performed. "
        f"The server will validate balances and execute the sell operation.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.TOKEN_TRADING_OPERATION


async def bundler_sell_percentage_choice(update: Update, context: CallbackContext) -> int:
    """
    Handle sell percentage choice - NO BALANCE CHECKING.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
    # Extract percentage from callback data
    callback_data = query.data
    if callback_data.startswith("bundler_sell_"):
        percentage_str = callback_data.replace("bundler_sell_", "")
        percentage = int(percentage_str)
    else:
        logger.error(f"Invalid callback data for sell percentage: {callback_data}")
        return ConversationState.TOKEN_TRADING_OPERATION
    
    # Store percentage in session
    session_manager.update_session_value(user.id, "sell_percentage", percentage)
    
    # Get stored token and operation data
    selected_token = session_manager.get_session_value(user.id, "selected_token")
    operation = session_manager.get_session_value(user.id, "token_operation")
    
    if not selected_token or not operation:
        await query.edit_message_text(
            "❌ **Session Error**\n\n"
            "Token or operation data missing. Please start over.",
            reply_markup=InlineKeyboardMarkup([[build_button("« Back to Token List", "view_tokens")]]),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.TOKEN_LIST
    
    token_name = selected_token.get('token_name', 'Unknown Token')
    mint_address = selected_token.get('mint_address', 'Unknown Address')
    
    operation_text = {
        "sell_dev": "🔴 **Sell from Dev Wallet**",
        "sell_bundled": "🔴 **Sell from Bundled Wallets**", 
        "sell_all": "🔴 **Sell from All Wallets**"
    }.get(operation, "Unknown Operation")
    
    # Show confirmation
    keyboard = [
        [build_button("✅ Execute Sell", "bundler_execute_sell")],
        [build_button("« Back to Percentage", "back_to_bundler_percentage")],
        [build_button("« Back to Token Options", "back_to_token_options")]
    ]
    
    await query.edit_message_text(
        f"{operation_text}\n\n"
        f"**Token:** {token_name}\n"
        f"**Mint:** `{mint_address}`\n"
        f"**Percentage:** {percentage}%\n\n"
        f"🔥 **Ready to Execute**\n\n"
        f"This will sell {percentage}% of tokens using direct API calls.\n\n"
        f"⚠️ **Important:**\n"
        f"• No balance checking will be performed\n"
        f"• Server validates everything\n"
        f"• Minimum SOL requirements:\n"
        f"  - DevWallet: 0.005 SOL\n"
        f"  - Other wallets: 0.003 SOL\n\n"
        f"Ready to proceed?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.TOKEN_TRADING_OPERATION


async def execute_bundler_sell_operation(update: Update, context: CallbackContext) -> int:
    """
    Execute the bundler sell operation using direct API calls - NO BALANCE CHECKING.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query

    # Refresh session before potentially long operation
    session_manager.refresh_session(user.id)
    
    # Get session data
    selected_token = session_manager.get_session_value(user.id, "selected_token")
    operation = session_manager.get_session_value(user.id, "token_operation")
    sell_percentage = session_manager.get_session_value(user.id, "sell_percentage")
    
    if not all([selected_token, operation, sell_percentage]):
        await query.edit_message_text(
            "❌ **Session Error**\n\n"
            "Required data missing. Please start over.",
            reply_markup=InlineKeyboardMarkup([[build_button("« Back to Token List", "view_tokens")]]),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.TOKEN_LIST
    
    token_name = selected_token.get('token_name', 'Unknown Token')
    mint_address = selected_token.get('mint_address', 'Unknown Address')
    
    # Show execution message
    await query.edit_message_text(
        f"🔄 **Executing Sell Operation**\n\n"
        f"**Token:** {token_name}\n"
        f"**Mint:** `{mint_address}`\n"
        f"**Percentage:** {sell_percentage}%\n"
        f"**Operation:** {operation}\n\n"
        f"⏳ Loading wallets and executing sell...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Load wallets from storage (no balance checks) using selected airdrop wallet from this flow
        from bot.utils.wallet_storage import bundled_wallet_storage
        
        selected_airdrop = (
            session_manager.get_session_value(user.id, "selected_selling_airdrop_wallet")
            or session_manager.get_session_value(user.id, "selected_airdrop_wallet")
        )
        airdrop_address = selected_airdrop.get('address') if isinstance(selected_airdrop, dict) else None
        
        if not airdrop_address:
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    "❌ **Error**\n\n"
                    "Could not determine the airdrop wallet for this sell operation.\n"
                    "Please reselect an airdrop wallet and try again."
                ),
                reply_markup=InlineKeyboardMarkup([[build_button("« Back to Airdrop Selection", "back_to_airdrop_selection")]]),
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationState.TOKEN_TRADING_OPERATION
        
        bundled_wallets = bundled_wallet_storage.load_bundled_wallets(airdrop_address, user.id)
        if not bundled_wallets:
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    "❌ **No Child Wallets Found**\n\n"
                    f"No bundled wallets found for airdrop wallet: `{airdrop_address[:8]}...{airdrop_address[-4:]}`\n\n"
                    "Please create bundled wallets through the bundling system."
                ),
                reply_markup=InlineKeyboardMarkup([[build_button("« Back to Airdrop Selection", "back_to_airdrop_selection")]]),
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationState.TOKEN_TRADING_OPERATION
        
        # Prepare wallets for API call
        wallets_data: List[Dict[str, str]] = []
        for wallet in bundled_wallets:
            if 'private_key' in wallet and 'name' in wallet:
                wallets_data.append({
                    "name": wallet['name'],
                    "privateKey": wallet['private_key']
                })
        
        if not wallets_data:
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    "❌ **Error**\n\n"
                    "No wallets available for sell operation."
                ),
                reply_markup=InlineKeyboardMarkup([[build_button("« Back to Token Options", "back_to_token_options")]]),
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationState.TOKEN_TRADING_OPERATION
        
        # Import and initialize client
        from bot.api.pumpfun_client import PumpFunClient
        pumpfun_client = PumpFunClient()
        slippage_bps = 2500
        
        # Execute sell operation according to type
        results: Dict[str, Any] = {}
        if operation == "sell_dev":
            dev_wallets = [w for w in wallets_data if w.get('name') == 'DevWallet']
            if not dev_wallets:
                raise Exception("DevWallet not found in wallet data")
            results = pumpfun_client.sell_dev_wallet(
                mint_address=mint_address,
                sell_percentage=sell_percentage,
                slippage_bps=slippage_bps,
                wallets=dev_wallets,
            )
        elif operation == "sell_bundled":
            bundled_only = [w for w in wallets_data if w.get('name') != 'DevWallet']
            if not bundled_only:
                raise Exception("No bundled wallets found in wallet data")
            results = pumpfun_client.batch_sell_token(
                mint_address=mint_address,
                sell_percentage=sell_percentage,
                slippage_bps=slippage_bps,
                wallets=bundled_only,
            )
        elif operation == "sell_all":
            all_results: Dict[str, Any] = {}
            # 1) Dev sell
            dev_wallets = [w for w in wallets_data if w.get('name') == 'DevWallet']
            if dev_wallets:
                dev_res = pumpfun_client.sell_dev_wallet(
                    mint_address=mint_address,
                    sell_percentage=sell_percentage,
                    slippage_bps=slippage_bps,
                    wallets=dev_wallets,
                )
                all_results['dev_wallet'] = dev_res
            # 2) Batch sell bundled
            bundled_only = [w for w in wallets_data if w.get('name') != 'DevWallet']
            if bundled_only:
                batch_res = pumpfun_client.batch_sell_token(
                    mint_address=mint_address,
                    sell_percentage=sell_percentage,
                    slippage_bps=slippage_bps,
                    wallets=bundled_only,
                )
                all_results['bundled_wallets'] = batch_res
            
            # Determine overall success
            def _op_success(res: Any) -> bool:
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
                    "operations": all_results,
                },
            }
        else:
            raise Exception(f"Unsupported operation: {operation}")
        
        # Prepare and send result message (align with token_trading_handler)
        keyboard = [[build_button("« Back to Token Options", "back_to_token_options")]]
        
        try:
            if isinstance(results, dict) and "data" in results:
                api_data = results["data"]
                
                def _is_sell_successful(data: Dict[str, Any]) -> bool:
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
                    bundle_results = api_data.get("bundleResults", [])
                    if bundle_results:
                        result_message += f"**Transaction Details:**\n"
                        for i, bundle in enumerate(bundle_results[:3]):
                            if bundle.get("success"):
                                bundle_id = bundle.get("bundleId", "N/A")
                                result_message += f"• Bundle {i+1}: `{bundle_id[:8]}...{bundle_id[-8:]}`\n"
                                transactions = bundle.get("transactions", [])
                                if transactions:
                                    result_message += f"  └ {len(transactions)} wallet(s) processed\n"
                        if len(bundle_results) > 3:
                            result_message += f"• ... and {len(bundle_results) - 3} more bundle(s)\n"
                    result_message += f"\n🎉 **Transaction completed! Check your wallets to see updated amounts!**\n\n"
                    result_message += f"**Please note that it may take some time for the transaction to be fully processed.**"
                else:
                    result_message = (
                        f"❌ **Sell Operation Failed**\n\n"
                        f"The sell operation was not successful.\n\n"
                        f"**Details:**\n"
                        f"• Token: `{mint_address[:8]}...{mint_address[-4:]}`\n"
                        f"• Attempted Percentage: {sell_percentage}%\n"
                        f"• Error: {api_data.get('message', 'Unknown error')}\n"
                    )
            else:
                logger.warning(f"Unexpected API response format: {results}")
                result_message = (
                    f"✅ **Sell Operation Completed**\n\n"
                    f"Your sell operation has been processed.\n\n"
                    f"Token: `{mint_address[:8]}...{mint_address[-4:]}`\n"
                    f"Percentage: {sell_percentage}%\n"
                )
        except Exception as _fmt_err:
            logger.exception(f"Error formatting sell results: {_fmt_err}")
            result_message = (
                f"✅ **Sell Operation Completed**\n\n"
                f"Token: `{mint_address[:8]}...{mint_address[-4:]}`\n"
                f"Percentage: {sell_percentage}%\n"
            )
        
        await context.bot.send_message(
            chat_id=user.id,
            text=result_message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
        )
        
        return ConversationState.TOKEN_TRADING_OPERATION
        
    except Exception as e:
        logger.error(f"Error executing bundler sell operation for user {user.id}: {e}")
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                f"❌ **Execution Error**\n\n"
                f"**Token:** {token_name}\n"
                f"**Error:** {str(e)}\n\n"
                f"Please try again or contact support."
            ),
            reply_markup=InlineKeyboardMarkup([
                [build_button("🔄 Try Again", "back_to_bundler_percentage")],
                [build_button("« Back to Token Options", "back_to_token_options")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.TOKEN_TRADING_OPERATION


async def start_bundler_management_workflow(update: Update, context: CallbackContext) -> int:
    """
    Start the bundler management workflow for token management.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
    # Get user's created tokens
    user_tokens = token_storage.get_user_tokens(user.id)
    
    if not user_tokens:
        # No tokens found, show message and redirect back
        keyboard = [[build_button("« Back to Activities", "back_to_activities")]]
        
        await query.edit_message_text(
            "📭 **No Tokens Found**\n\n"
            "You haven't created any tokens yet.\n\n"
            "Use 'Token Bundling (PumpFun)' to create your first token!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.ACTIVITY_SELECTION
    
    # Show bundler management selection
    keyboard = [
        [build_button("📋 View Created Tokens", "view_tokens")],
        [build_button("« Back to Activities", "back_to_activities")]
    ]
    
    await query.edit_message_text(
        format_bundler_management_selection_message(),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.BUNDLER_MANAGEMENT
