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
        
        # For now, show placeholder message
        keyboard = [[build_button("« Back to Token Options", "back_to_token_options")]]
        
        operation_text = {
            "buy_dev": "🟢 **Buy with Dev Wallet**",
            "buy_bundled": "🟢 **Buy with Bundled Wallets**", 
            "buy_all": "🟢 **Buy with All Wallets**",
            "sell_dev": "🔴 **Sell with Dev Wallet**",
            "sell_bundled": "🔴 **Sell with Bundled Wallets**",
            "sell_all": "🔴 **Sell with All Wallets**"
        }.get(operation, "Unknown Operation")
        
        token_name = selected_token.get('token_name', 'Unknown Token')
        
        await query.edit_message_text(
            f"{operation_text}\n\n"
            f"**Token:** {token_name}\n\n"
            f"🚧 **Coming Soon**\n\n"
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
