"""
Token Configuration Handler Module

This module contains all the handlers for token parameter configuration,
including name, ticker, description input and image upload handling.
"""

from typing import Dict, List, Any, Optional
import asyncio
import time
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext
from loguru import logger

from bot.config import ConversationState, CallbackPrefix
from bot.state.session_manager import session_manager
from bot.utils.keyboard_utils import build_button, build_keyboard
from bot.utils.validation_utils import (
    validate_token_name,
    validate_token_ticker,
    validate_token_description,
    log_validation_result
)
from bot.utils.message_utils import (
    format_token_parameter_request,
    format_token_creation_preview
)


async def token_parameter_input(update: Update, context: CallbackContext) -> int:
    """
    Handle token parameter input from user.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.message.from_user
    parameter_value = update.message.text.strip()
    
    # Get current parameter being collected
    current_param = session_manager.get_session_value(user.id, "current_token_parameter")
    token_params = session_manager.get_session_value(user.id, "token_params") or {}
    
    # Validate the parameter based on type
    if current_param == "name":
        is_valid, value_or_error = validate_token_name(parameter_value)
    elif current_param == "ticker":
        is_valid, value_or_error = validate_token_ticker(parameter_value)
    elif current_param == "description":
        is_valid, value_or_error = validate_token_description(parameter_value)
    else:
        is_valid, value_or_error = False, "Unknown parameter"
    
    # Extract validated value and error message
    if is_valid:
        validated_value = value_or_error
        error_msg = ""
    else:
        validated_value = None
        error_msg = value_or_error
    
    log_validation_result(f"token_{current_param}", parameter_value, is_valid, error_msg, user.id)
    
    if not is_valid:
        keyboard = InlineKeyboardMarkup([
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await update.message.reply_text(
            f"❌ **Invalid {current_param.title()}**\n\n{error_msg}\n\n"
            f"Please try again:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.TOKEN_PARAMETER_INPUT
    
    # Store validated parameter
    token_params[current_param] = validated_value
    session_manager.update_session_value(user.id, "token_params", token_params)
    
    # Determine next parameter or proceed to image upload
    parameter_order = ["name", "ticker", "description"]  # Removed image_url - handled separately
    current_index = parameter_order.index(current_param)
    
    if current_index + 1 < len(parameter_order):
        # Move to next parameter
        next_param = parameter_order[current_index + 1]
        session_manager.update_session_value(user.id, "current_token_parameter", next_param)
        
        keyboard = InlineKeyboardMarkup([
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        # Get parameter description based on type
        param_descriptions = {
            "ticker": "the token symbol/ticker (e.g., 'MAT')",
            "description": "a description of your token and its purpose"
        }
        
        await update.message.reply_text(
            format_token_parameter_request(next_param, param_descriptions.get(next_param, "this parameter")),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.TOKEN_PARAMETER_INPUT
    else:
        # Basic parameters collected, proceed to image upload step
        token_params["initial_supply"] = 1000000000  # Standard supply
        session_manager.update_session_value(user.id, "token_params", token_params)
        
        # Request token image upload
        keyboard = InlineKeyboardMarkup([
            [build_button("⏭️ Skip Image", "skip_image")],
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        message = (
            "🖼️ **Token Image (Optional)**\n\n"
            "You can upload an image for your token:\n"
            "• Send any photo directly to this chat\n"
            "• Recommended: Square images (500x500px or larger)\n"
            "• Supported formats: JPG, PNG\n\n"
            "Or skip this step to create token without image."
        )
        
        await update.message.reply_text(
            message,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.TOKEN_IMAGE_UPLOAD


async def process_token_image_upload(update: Update, context: CallbackContext) -> int:
    """
    Process uploaded image from Telegram for token creation with Pump.fun optimization.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.message.from_user
    
    try:
        # Import the image processor
        from bot.utils.image_utils import TelegramImageProcessor
        
        # Get the largest photo size for best quality
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        logger.info(f"User {user.id} uploading image: {photo.file_size} bytes")
        
        # Send processing message
        processing_msg = await update.message.reply_text(
            "🔄 **Processing Image...**\n\n"
            "Converting your image for optimal Pump.fun compatibility...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Process with enhanced pipeline
        image_processor = TelegramImageProcessor()
        success, message, final_path, processing_info = await image_processor.download_and_process(file, user.id)
        
        if not success:
            # Handle processing failure
            keyboard = InlineKeyboardMarkup([
                [build_button("🔄 Try Another Image", "retry_image_upload")],
                [build_button("⏭️ Skip Image", "skip_image")],
                [build_button("« Back to Activities", "back_to_activities")]
            ])
            
            await processing_msg.edit_text(
                f"❌ **Image Processing Failed**\n\n{message}\n\n"
                "Please try uploading a different image or skip this step.",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.TOKEN_IMAGE_UPLOAD
        
        # Store successful processing results
        session_manager.update_session_value(user.id, "token_image_local_path", final_path)
        session_manager.update_session_value(user.id, "has_custom_image", True)
        session_manager.update_session_value(user.id, "image_processing_info", processing_info)
        
        # Clean up old files but keep the latest
        image_processor.cleanup_temp_files(user.id, keep_latest=True)
        
        # Get file info for display
        file_info = image_processor.get_file_info(final_path)
        processing_time = processing_info.get("processing_time", 0)
        
        # Create success message with details
        success_details = []
        if file_info:
            success_details.append(f"📐 Size: {file_info['width']}x{file_info['height']} pixels")
            success_details.append(f"💾 File size: {file_info['size_mb']} MB")
        
        if processing_time > 0:
            success_details.append(f"⏱️ Processed in {processing_time:.1f}s")
        
        success_text = "✅ **Image Optimized for Pump.fun!**\n\n" + "\n".join(success_details)
        
        keyboard = InlineKeyboardMarkup([
            [build_button("Continue to Preview", "proceed_to_preview")]
        ])
        
        await processing_msg.edit_text(
            success_text + "\n\nReady to proceed with token creation!",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        logger.info(f"Successfully processed image for user {user.id}: {final_path}")
        
        return ConversationState.TOKEN_IMAGE_UPLOAD
        
    except Exception as e:
        logger.error(f"Error processing image upload for user {user.id}: {e}")
        
        keyboard = InlineKeyboardMarkup([
            [build_button("🔄 Try Again", "retry_image_upload")],
            [build_button("⏭️ Skip Image", "skip_image")],
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await update.message.reply_text(
            "❌ **Unexpected Error**\n\n"
            f"An error occurred while processing your image: {str(e)}\n\n"
            "Please try again or skip this step.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.TOKEN_IMAGE_UPLOAD


async def retry_image_upload(update: Update, context: CallbackContext) -> int:
    """
    Allow user to retry image upload after failure.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer("Ready for new image")
    
    keyboard = InlineKeyboardMarkup([
        [build_button("⏭️ Skip Image", "skip_image")],
        [build_button("« Back to Activities", "back_to_activities")]
    ])
    
    message = (
        "🖼️ **Upload New Image**\n\n"
        "Please send a new photo for your token:\n"
        "• Supported formats: JPG, PNG\n"
        "• Will be optimized to 500x500 for Pump.fun\n"
        "• Maximum size: 20MB\n\n"
        "Send your image now or skip this step."
    )
    
    await query.edit_message_text(
        message,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.TOKEN_IMAGE_UPLOAD


async def skip_image_upload(update: Update, context: CallbackContext) -> int:
    """
    Skip image upload and proceed to token preview.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer("Proceeding without image")
    
    # Set no image flags in session
    session_manager.update_session_value(user.id, "has_custom_image", False)
    session_manager.update_session_value(user.id, "token_image_local_path", None)
    
    logger.info(f"User {user.id} skipped token image upload")
    
    # Get token params and show preview
    token_params = session_manager.get_session_value(user.id, "token_params") or {}
    
    keyboard = InlineKeyboardMarkup([
        [build_button("💰 Configure Buy Amounts", "configure_buy_amounts")],
        [build_button("✏️ Edit Parameters", "edit_token_parameters")],
        [build_button("« Back to Activities", "back_to_activities")]
    ])
    
    await query.edit_message_text(
        format_token_creation_preview(token_params),
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.TOKEN_CREATION_PREVIEW


async def proceed_to_preview(update: Update, context: CallbackContext) -> int:
    """
    Proceed to token creation preview after image upload.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Get token params and show preview
    token_params = session_manager.get_session_value(user.id, "token_params") or {}
    has_image = session_manager.get_session_value(user.id, "has_custom_image", False)
    image_path = session_manager.get_session_value(user.id, "token_image_local_path")
    
    # Add enhanced image status to preview
    preview_text = format_token_creation_preview(token_params)
    
    if has_image and image_path:
        # Get detailed image information
        try:
            from bot.utils.image_utils import TelegramImageProcessor
            image_processor = TelegramImageProcessor()
            file_info = image_processor.get_file_info(image_path)
            
            if file_info:
                pump_ready = "✅ Pump.fun ready" if file_info.get("pump_fun_ready", False) else "🔧 Optimized"
                preview_text += f"\n🖼️ **Image:** {pump_ready} ({file_info['width']}x{file_info['height']}, {file_info['size_mb']}MB)"
            else:
                preview_text += "\n🖼️ **Image:** Custom image uploaded ✅"
        except Exception:
            preview_text += "\n🖼️ **Image:** Custom image uploaded ✅"
    else:
        preview_text += "\n🖼️ **Image:** No image (default will be used)"
    
    keyboard = InlineKeyboardMarkup([
        [build_button("💰 Configure Buy Amounts", "configure_buy_amounts")],
        [build_button("✏️ Edit Parameters", "edit_token_parameters")],
        [build_button("« Back to Activities", "back_to_activities")]
    ])
    
    await query.edit_message_text(
        preview_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.TOKEN_CREATION_PREVIEW


async def edit_token_parameters(update: Update, context: CallbackContext) -> int:
    """
    Allow user to edit token parameters by restarting parameter input.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Reset to first parameter
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
