"""
Bundling Handler Module

This module contains all the handlers for the PumpFun token bundling workflow,
including airdrop wallet management, bundled wallet creation, token creation,
and bundle operation execution.
"""

from typing import Dict, List, Any, Optional
import asyncio
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext
from loguru import logger

from bot.config import ConversationState, CallbackPrefix
from bot.utils.keyboard_utils import build_button, build_keyboard
from bot.utils.validation_utils import (
    validate_bundled_wallets_count,
    validate_token_name,
    validate_token_ticker,
    validate_token_supply,
    validate_token_description,
    validate_image_url,
    validate_buy_amount,
    log_validation_result
)
from bot.utils.message_utils import (
    format_token_creation_start_message,
    format_token_parameter_request,
    format_token_creation_preview,
    format_bundle_operation_progress,
    format_bundle_operation_results,
    format_pumpfun_error_message,
    format_bundled_wallets_creation_message,
    format_bundled_wallets_created_message,
    format_existing_bundled_wallets_selected_message,
    format_buy_amounts_config_message,
    format_buy_amount_request,
    format_buy_amounts_preview,
    format_buy_amounts_execution_progress,
    format_wallet_balance_check_message,
    format_wallet_balance_result_message,
    format_wallet_funding_required_message,
    format_wallet_funding_progress_message,
    format_wallet_funding_complete_message
)
from bot.state.session_manager import session_manager
from bot.utils.wallet_storage import airdrop_wallet_storage, bundled_wallet_storage


async def create_airdrop_wallet(update: Update, context: CallbackContext) -> int:
    """
    Handle airdrop wallet creation.
    
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
        # Get PumpFun client from session
        pumpfun_client = session_manager.get_session_value(user.id, "pumpfun_client")
        if not pumpfun_client:
            logger.error(f"PumpFun client not found in session for user {user.id}")
            
            keyboard = [[build_button("« Back to Activities", "back_to_activities")]]
            await query.edit_message_text(
                "❌ **Setup Error**\n\n"
                "PumpFun client not found. Please restart the bundling workflow.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationState.ACTIVITY_SELECTION
        
        # Show initial progress message for cold start scenarios
        await query.edit_message_text(
            "🔄 **Creating Airdrop Wallet...**\n\n"
            "⏳ Initializing wallet creation. This may take a moment if the API is starting up...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Create airdrop wallet using PumpFun API
        logger.info(f"Creating airdrop wallet for user {user.id}")
        wallet_info = pumpfun_client.create_airdrop_wallet()
        
        # Store wallet information in session
        session_manager.update_session_value(user.id, "airdrop_wallet", wallet_info["address"])
        session_manager.update_session_value(user.id, "airdrop_private_key", wallet_info.get("private_key", ""))
        
        # Save airdrop wallet to data folder for persistent storage
        try:
            airdrop_wallet_storage.save_airdrop_wallet(
                wallet_address=wallet_info["address"],
                wallet_data=wallet_info,
                user_id=user.id
            )
            logger.info(
                f"Saved airdrop wallet to persistent storage for user {user.id}",
                extra={"user_id": user.id, "wallet_address": wallet_info["address"]}
            )
        except Exception as storage_error:
            logger.warning(
                f"Failed to save airdrop wallet to persistent storage: {str(storage_error)}",
                extra={"user_id": user.id, "wallet_address": wallet_info["address"]}
            )
            # Continue execution even if storage fails - session data is still available
        
        logger.info(
            f"Created airdrop wallet for user {user.id}",
            extra={"user_id": user.id, "wallet_address": wallet_info["address"]}
        )
        
        # Show success message and proceed to bundled wallets count
        keyboard = [[build_button("Continue", "continue_to_bundled_count")]]
        await query.edit_message_text(
            f"✅ **Airdrop Wallet Created**\n\n"
            f"**Address:** `{wallet_info['address']}`\n\n"
            f"This wallet will be used to fund your bundled wallets for token operations.\n"
            f"Make sure to fund this wallet with SOL before proceeding.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLED_WALLETS_COUNT
        
    except Exception as e:
        logger.error(
            f"Failed to create airdrop wallet for user {user.id}: {str(e)}",
            extra={"user_id": user.id}
        )
        
        # Enhanced error handling for cold start scenarios
        is_timeout_error = "timeout" in str(e).lower()
        is_connection_error = "connection" in str(e).lower()
        
        if is_timeout_error or is_connection_error:
            keyboard = [
                [build_button("🔄 Retry (Recommended)", "create_airdrop_wallet")],
                [build_button("Wait & Retry", "wait_and_retry_airdrop")],
                [build_button("« Back to Activities", "back_to_activities")]
            ]
            
            error_message = (
                "🕒 **API Cold Start Detected**\n\n"
                "The PumpFun API appears to be starting up. This is normal for cloud-hosted services.\n\n"
                "**What happened:** The service was in sleep mode and needs a moment to wake up.\n\n"
                "**Recommended action:** Click 'Retry' - the service should be ready now.\n\n"
                f"**Technical details:** {str(e)[:100]}..."
            )
        else:
            keyboard = [
                [build_button("Try Again", "create_airdrop_wallet")],
                [build_button("« Back to Activities", "back_to_activities")]
            ]
            error_message = format_pumpfun_error_message("airdrop_wallet_creation", str(e))
        
        await query.edit_message_text(
            error_message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLING_WALLET_SETUP


async def wait_and_retry_airdrop(update: Update, context: CallbackContext) -> int:
    """
    Handle wait and retry for airdrop wallet creation after cold start.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Show waiting message
    await query.edit_message_text(
        "⏳ **Waiting for API to fully initialize...**\n\n"
        "Giving the service a moment to complete startup. This will take about 10 seconds.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Wait for 10 seconds to allow API to fully initialize
    await asyncio.sleep(10)
    
    # Now retry the wallet creation
    return await create_airdrop_wallet(update, context)


async def import_airdrop_wallet(update: Update, context: CallbackContext) -> int:
    """
    Handle airdrop wallet import.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Request private key from user
    keyboard = [[build_button("« Back to Activities", "back_to_activities")]]
    await query.edit_message_text(
        "🔐 **Import Airdrop Wallet**\n\n"
        "Please send your airdrop wallet private key.\n\n"
        "⚠️ **Security Note:** Your private key will be encrypted and stored securely. "
        "Never share your private key with anyone else.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.IMPORT_AIRDROP_WALLET


async def process_airdrop_wallet_import(update: Update, context: CallbackContext) -> int:
    """
    Process the imported airdrop wallet private key.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.message.from_user
    private_key = update.message.text.strip()
    
    try:
        # Get PumpFun client from session
        pumpfun_client = session_manager.get_session_value(user.id, "pumpfun_client")
        if not pumpfun_client:
            await update.message.reply_text(
                "❌ PumpFun client not found. Please restart the bundling workflow."
            )
            return ConversationState.ACTIVITY_SELECTION
        
        # Show progress message
        progress_message = await update.message.reply_text(
            "🔄 **Importing Airdrop Wallet...**\n\n"
            "⏳ Processing your private key. This may take a moment...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Import wallet using PumpFun API
        logger.info(f"Importing airdrop wallet for user {user.id}")
        wallet_info = pumpfun_client.create_airdrop_wallet(private_key)
        
        # Store wallet information in session
        session_manager.update_session_value(user.id, "airdrop_wallet", wallet_info["address"])
        session_manager.update_session_value(user.id, "airdrop_private_key", wallet_info.get("private_key", private_key))
        
        # Save imported airdrop wallet to data folder for persistent storage
        try:
            # Include the private key in wallet data for imported wallets
            wallet_data_with_key = {
                **wallet_info,
                "private_key": private_key,
                "imported": True
            }
            airdrop_wallet_storage.save_airdrop_wallet(
                wallet_address=wallet_info["address"],
                wallet_data=wallet_data_with_key,
                user_id=user.id
            )
            logger.info(
                f"Saved imported airdrop wallet to persistent storage for user {user.id}",
                extra={"user_id": user.id, "wallet_address": wallet_info["address"]}
            )
        except Exception as storage_error:
            logger.warning(
                f"Failed to save imported airdrop wallet to persistent storage: {str(storage_error)}",
                extra={"user_id": user.id, "wallet_address": wallet_info["address"]}
            )
            # Continue execution even if storage fails - session data is still available
        
        logger.info(
            f"Imported airdrop wallet for user {user.id}",
            extra={"user_id": user.id, "wallet_address": wallet_info["address"]}
        )
        
        # Show success message and proceed
        keyboard = InlineKeyboardMarkup([
            [build_button("Continue", "continue_to_bundled_count")]
        ])
        
        await progress_message.edit_text(
            f"✅ **Airdrop Wallet Imported**\n\n"
            f"**Address:** `{wallet_info['address']}`\n\n"
            f"Wallet imported successfully. Ready to proceed with bundled wallet creation.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLED_WALLETS_COUNT
        
    except Exception as e:
        logger.error(
            f"Failed to import airdrop wallet for user {user.id}: {str(e)}",
            extra={"user_id": user.id}
        )
        
        # Enhanced error handling for cold start scenarios
        is_timeout_error = "timeout" in str(e).lower()
        is_connection_error = "connection" in str(e).lower()
        
        if is_timeout_error or is_connection_error:
            keyboard = InlineKeyboardMarkup([
                [build_button("🔄 Retry Import", "import_airdrop_wallet")],
                [build_button("« Back to Activities", "back_to_activities")]
            ])
            
            error_message = (
                "🕒 **API Cold Start During Import**\n\n"
                "The API was initializing during your import. Please try importing your wallet again.\n\n"
                "Your private key was not saved - please re-enter it when you retry."
            )
        else:
            keyboard = InlineKeyboardMarkup([
                [build_button("Try Again", "import_airdrop_wallet")],
                [build_button("« Back to Activities", "back_to_activities")]
            ])
            error_message = format_pumpfun_error_message("airdrop_wallet_import", str(e))
        
        await update.message.reply_text(
            error_message,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLING_WALLET_SETUP


async def continue_to_bundled_wallets_setup(update: Update, context: CallbackContext) -> int:
    """
    Handle continuation to bundled wallets setup after airdrop wallet selection.
    Now checks for existing bundled wallets first.
    
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
        # Get airdrop wallet address from session
        airdrop_wallet_address = session_manager.get_session_value(user.id, "airdrop_wallet")
        if not airdrop_wallet_address:
            raise Exception("Airdrop wallet address not found in session")
        
        logger.info(
            f"Checking for existing bundled wallets for airdrop wallet {airdrop_wallet_address}",
            extra={"user_id": user.id, "airdrop_wallet": airdrop_wallet_address}
        )
        
        # Debug: Show what files exist in the bundled wallets directory
        try:
            import os
            bundled_dir = "ninjabot/data/bundled_wallets"
            if os.path.exists(bundled_dir):
                files = os.listdir(bundled_dir)
                user_files = [f for f in files if f.startswith(f"bundled_{user.id}_")]
                logger.info(
                    f"Debug: Found {len(user_files)} bundled wallet files for user {user.id}: {user_files}",
                    extra={"user_id": user.id, "files": user_files}
                )
            else:
                logger.warning(f"Debug: Bundled wallets directory does not exist: {bundled_dir}")
        except Exception as debug_error:
            logger.warning(f"Debug: Error checking bundled wallets directory: {debug_error}")
        
        # Check for existing bundled wallets for this airdrop wallet
        existing_bundled_wallets = bundled_wallet_storage.load_bundled_wallets(airdrop_wallet_address, user.id)
        
        logger.info(
            f"Found {len(existing_bundled_wallets)} existing bundled wallets",
            extra={"user_id": user.id, "airdrop_wallet": airdrop_wallet_address, "wallet_count": len(existing_bundled_wallets)}
        )
        
        if existing_bundled_wallets and len(existing_bundled_wallets) > 0:
            # Store existing wallets in session in the format expected by the system
            wallet_addresses = [wallet["address"] for wallet in existing_bundled_wallets if "address" in wallet]
            
            # Store the wallets in session in the expected format
            session_manager.update_session_value(user.id, "bundled_wallets", wallet_addresses)
            session_manager.update_session_value(user.id, "bundled_wallets_data", existing_bundled_wallets)
            session_manager.update_session_value(user.id, "bundled_wallets_count", len(wallet_addresses))
            
            # Also store private keys separately for compatibility
            wallet_private_keys = [wallet.get("private_key", "") for wallet in existing_bundled_wallets]
            session_manager.update_session_value(user.id, "bundled_private_keys", wallet_private_keys)
            
            logger.info(
                f"Using {len(wallet_addresses)} existing bundled wallets, proceeding directly to token creation",
                extra={"user_id": user.id, "airdrop_wallet": airdrop_wallet_address, "wallet_count": len(wallet_addresses)}
            )
            
            # Skip bundled wallet creation and go directly to token creation
            keyboard = InlineKeyboardMarkup([
                [build_button("Start Token Creation", "start_token_creation")]
            ])
            
            await query.edit_message_text(
                format_existing_bundled_wallets_selected_message(len(wallet_addresses), wallet_addresses),
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.TOKEN_CREATION_START
        else:
            # No existing bundled wallets, proceed to creation
            await query.edit_message_text(
                format_bundled_wallets_creation_message(),
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(
                f"No existing bundled wallets found for user {user.id}, proceeding to creation",
                extra={"user_id": user.id, "airdrop_wallet": airdrop_wallet_address}
            )
            
            return ConversationState.BUNDLED_WALLETS_COUNT
        
    except Exception as e:
        logger.error(
            f"Failed to check for existing bundled wallets for user {user.id}: {str(e)}",
            extra={"user_id": user.id},
            exc_info=True
        )
        
        # On error, proceed to creation as fallback
        await query.edit_message_text(
            format_bundled_wallets_creation_message(),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLED_WALLETS_COUNT


async def bundled_wallets_count(update: Update, context: CallbackContext) -> int:
    """
    Handle bundled wallets count input.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.message.from_user
    count_input = update.message.text.strip()
    
    # Validate wallet count
    is_valid, wallet_count_or_error = validate_bundled_wallets_count(count_input)
    if is_valid:
        wallet_count = wallet_count_or_error
        error_msg = ""
    else:
        wallet_count = 0
        error_msg = wallet_count_or_error
    log_validation_result("bundled_wallets_count", count_input, is_valid, error_msg, user.id)
    
    if not is_valid:
        keyboard = InlineKeyboardMarkup([
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await update.message.reply_text(
            f"❌ **Invalid Wallet Count**\n\n{error_msg}\n\n"
            f"Please enter a number between 5 and 50:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.BUNDLED_WALLETS_COUNT
    
    # Store wallet count in session
    session_manager.update_session_value(user.id, "bundled_wallets_count", wallet_count)
    
    logger.info(
        f"User {user.id} set bundled wallets count to {wallet_count}",
        extra={"user_id": user.id, "wallet_count": wallet_count}
    )
    
    try:
        # Get PumpFun client from session
        pumpfun_client = session_manager.get_session_value(user.id, "pumpfun_client")
        if not pumpfun_client:
            raise Exception("PumpFun client not found in session")
        
        # Show progress message
        progress_message = await update.message.reply_text(
            "🔄 **Creating Bundled Wallets...**\n\n"
            f"Creating {wallet_count} bundled wallets for token operations.\n"
            "⏳ This may take a moment...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Create bundled wallets using PumpFun API
        logger.info(f"Creating {wallet_count} bundled wallets for user {user.id}")
        bundled_wallets_result = pumpfun_client.create_bundled_wallets(count=wallet_count)
        
        # Store bundled wallets in session
        session_manager.update_session_value(user.id, "bundled_wallets", bundled_wallets_result.get("wallets", []))
        session_manager.update_session_value(user.id, "bundled_private_keys", bundled_wallets_result.get("private_keys", []))
        
        # Save bundled wallets to persistent storage
        try:
            airdrop_wallet_address = session_manager.get_session_value(user.id, "airdrop_wallet")
            if airdrop_wallet_address:
                bundled_wallet_storage.save_bundled_wallets(
                    airdrop_wallet_address=airdrop_wallet_address,
                    bundled_wallets_data=bundled_wallets_result,
                    user_id=user.id,
                    wallet_count=wallet_count
                )
                logger.info(
                    f"Saved {wallet_count} bundled wallets to persistent storage for user {user.id}",
                    extra={"user_id": user.id, "airdrop_wallet_address": airdrop_wallet_address, "wallet_count": wallet_count}
                )
            else:
                logger.warning(
                    f"No airdrop wallet address found in session for user {user.id}, skipping persistent storage",
                    extra={"user_id": user.id}
                )
        except Exception as storage_error:
            logger.warning(
                f"Failed to save bundled wallets to persistent storage: {str(storage_error)}",
                extra={"user_id": user.id, "wallet_count": wallet_count}
            )
            # Continue execution even if storage fails - session data is still available
        
        # Import the message formatter from utils
        from bot.utils.message_utils import format_bundled_wallets_created_message
        
        # Show success message and proceed to token creation
        keyboard = InlineKeyboardMarkup([
            [build_button("Start Token Creation", "start_token_creation")]
        ])
        
        wallet_details = bundled_wallets_result.get("wallets", [])
        
        await progress_message.edit_text(
            format_bundled_wallets_created_message(wallet_count, wallet_details),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.TOKEN_CREATION_START
        
    except Exception as e:
        logger.error(
            f"Failed to create bundled wallets for user {user.id}: {str(e)}",
            extra={"user_id": user.id, "wallet_count": wallet_count}
        )
        
        keyboard = InlineKeyboardMarkup([
            [build_button("Try Again", "retry_bundled_wallets")],
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await update.message.reply_text(
            format_pumpfun_error_message("bundled_wallets_creation", str(e)),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLED_WALLETS_COUNT


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
    elif current_param == "image_url":
        is_valid, value_or_error = validate_image_url(parameter_value)
    elif current_param == "initial_supply":
        is_valid, value_or_error = validate_token_supply(parameter_value)
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
    
    # Determine next parameter or proceed to preview
    parameter_order = ["name", "ticker", "description", "image_url", "initial_supply"]
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
            "description": "a description of your token and its purpose",
            "image_url": "the URL of your token's image/logo (optional)",
            "initial_supply": "the initial token supply (e.g., 1000000)"
        }
        
        await update.message.reply_text(
            format_token_parameter_request(next_param, param_descriptions.get(next_param, "this parameter")),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.TOKEN_PARAMETER_INPUT
    else:
        # All parameters collected, show preview
        keyboard = InlineKeyboardMarkup([
            [build_button("💰 Configure Buy Amounts", "configure_buy_amounts")],
            [build_button("✏️ Edit Parameters", "edit_token_parameters")],
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await update.message.reply_text(
            format_token_creation_preview(token_params),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.TOKEN_CREATION_PREVIEW


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
    
    # Initialize buy amounts configuration
    wallet_names = ["DevWallet", "First Bundled Wallet 1", "First Bundled Wallet 2", 
                   "First Bundled Wallet 3", "First Bundled Wallet 4"]
    
    session_manager.update_session_value(user.id, "buy_amounts_wallets", wallet_names)
    session_manager.update_session_value(user.id, "current_buy_wallet_index", 0)
    session_manager.update_session_value(user.id, "buy_amounts", {})
    
    # Show the buy amounts configuration intro
    keyboard = InlineKeyboardMarkup([
        [build_button("Start Configuration", "start_buy_amounts_input")],
        [build_button("« Back to Token Preview", "back_to_token_preview")]
    ])
    
    token_params = session_manager.get_session_value(user.id, "token_params")
    token_name = token_params.get("name", "your token") if token_params else "your token"
    
    await query.edit_message_text(
        f"💰 **Configure Buy Amounts**\n\n"
        f"Now let's configure how much SOL each wallet should spend to buy **{token_name}** during token creation.\n\n"
        f"**Wallets to configure:**\n"
        f"• DevWallet (main development wallet)\n"
        f"• First Bundled Wallet 1-4 (trading wallets)\n\n"
        f"💡 **Important:** Configure these amounts before we check your airdrop wallet balance and fund the bundled wallets.",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.BUY_AMOUNTS_CONFIG


async def buy_amounts_input(update: Update, context: CallbackContext) -> int:
    """
    Handle buy amount input from user.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.message.from_user
    amount_input = update.message.text.strip()
    
    # Get current configuration
    wallet_names = session_manager.get_session_value(user.id, "buy_amounts_wallets")
    current_index = session_manager.get_session_value(user.id, "current_buy_wallet_index")
    buy_amounts = session_manager.get_session_value(user.id, "buy_amounts") or {}
    
    if not wallet_names or current_index is None:
        await update.message.reply_text(
            "❌ Configuration error. Please restart the process.",
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.ACTIVITY_SELECTION
    
    current_wallet = wallet_names[current_index]
    
    # Validate buy amount
    is_valid, amount_or_error = validate_buy_amount(amount_input)
    log_validation_result(f"buy_amount_{current_wallet}", amount_input, is_valid, 
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
    
    # Store validated amount
    buy_amounts[current_wallet] = amount_or_error
    session_manager.update_session_value(user.id, "buy_amounts", buy_amounts)
    
    # Check if we need to ask for more wallets
    if current_index + 1 < len(wallet_names):
        # Move to next wallet
        next_index = current_index + 1
        session_manager.update_session_value(user.id, "current_buy_wallet_index", next_index)
        
        keyboard = InlineKeyboardMarkup([
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await update.message.reply_text(
            format_buy_amount_request(wallet_names[next_index], next_index + 1, len(wallet_names)),
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
            format_buy_amounts_preview(buy_amounts, "Token will be created after funding"),
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





async def bundle_operation_progress(update: Update, context: CallbackContext) -> int:
    """
    Execute bundle operations and track progress.
    
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
        bundled_wallets = session_manager.get_session_value(user.id, "bundled_wallets")
        bundled_private_keys = session_manager.get_session_value(user.id, "bundled_private_keys")
        token_address = session_manager.get_session_value(user.id, "token_address")
        
        if not all([pumpfun_client, bundled_wallets, bundled_private_keys, token_address]):
            raise Exception("Missing required data for bundle operations")
        
        # Calculate buy amounts (equal distribution)
        base_amount = 0.05  # 0.05 SOL per wallet
        buy_amounts = [base_amount] * len(bundled_wallets)
        
        # Show progress message
        await query.edit_message_text(
            format_bundle_operation_progress("starting", {
                "total_wallets": len(bundled_wallets),
                "total_sol": sum(buy_amounts),
                "token_address": token_address
            }),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Execute batch buy operations
        logger.info(f"Starting bundle operations for user {user.id}")
        start_time = time.time()
        
        # Use the actual batch_buy_token method signature
        batch_result = pumpfun_client.batch_buy_token(
            mint_address=token_address,
            sol_amount_per_wallet=base_amount,
            slippage_bps=2500
        )
        
        execution_time = time.time() - start_time
        
        # Store operation results
        operation_results = {
            "successful_buys": batch_result["successful_buys"],
            "failed_buys": batch_result["failed_buys"],
            "total_sol_spent": batch_result["total_sol_spent"],
            "signatures": batch_result["signatures"],
            "execution_time": execution_time
        }
        
        session_manager.update_session_value(user.id, "bundle_operation_results", operation_results)
        
        logger.info(
            f"Bundle operations completed for user {user.id}",
            extra={
                "user_id": user.id,
                "successful_buys": batch_result["successful_buys"],
                "failed_buys": batch_result["failed_buys"],
                "execution_time": execution_time
            }
        )
        
        # Show results
        keyboard = InlineKeyboardMarkup([
            [build_button("🎉 Start New Bundle", "back_to_activities")],
            [build_button("📊 View Transaction Details", "view_transaction_details")]
        ])
        
        # Prepare results data with token address included
        results_with_token = operation_results.copy()
        results_with_token["token_address"] = token_address
        
        await query.edit_message_text(
            format_bundle_operation_results(results_with_token),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLE_OPERATION_COMPLETE
        
    except Exception as e:
        logger.error(
            f"Bundle operations failed for user {user.id}: {str(e)}",
            extra={"user_id": user.id}
        )
        
        keyboard = InlineKeyboardMarkup([
            [build_button("Try Again", "start_bundle_operations")],
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await query.edit_message_text(
            format_pumpfun_error_message("bundle_operations", str(e)),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLE_OPERATION_PROGRESS


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
            session_manager.update_session_value(user.id, "airdrop_wallet", wallet_address)
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
            session_manager.update_session_value(user.id, "airdrop_wallet", wallet_address)
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


async def check_wallet_balance(update: Update, context: CallbackContext) -> int:
    """
    Check airdrop wallet balance to ensure sufficient funds for token creation and buys.
    
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
        airdrop_wallet = session_manager.get_session_value(user.id, "airdrop_wallet")
        buy_amounts = session_manager.get_session_value(user.id, "buy_amounts")
        
        if not all([pumpfun_client, airdrop_wallet, buy_amounts]):
            raise Exception("Missing required session data for balance check")
        
        # Show checking message
        await query.edit_message_text(
            format_wallet_balance_check_message(airdrop_wallet, buy_amounts),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Check wallet balance using PumpFun client
        logger.info(f"Checking airdrop wallet balance for user {user.id}")
        balance_info = pumpfun_client.get_wallet_balance(airdrop_wallet)
        current_balance = balance_info.get("balance", 0)
        
        # Calculate required balance (buy amounts + gas fees + buffer)
        total_buy_amount = sum(buy_amounts.values())
        gas_fees_estimate = total_buy_amount * 0.05  # 5% for gas fees
        buffer = 0.01  # Small buffer
        required_balance = total_buy_amount + gas_fees_estimate + buffer
        
        has_sufficient = current_balance >= required_balance
        
        # Store balance check results
        session_manager.update_session_value(user.id, "balance_check_result", {
            "current_balance": current_balance,
            "required_balance": required_balance,
            "has_sufficient": has_sufficient
        })
        
        logger.info(
            f"Balance check for user {user.id}: {current_balance:.6f} SOL (required: {required_balance:.6f})",
            extra={
                "user_id": user.id,
                "current_balance": current_balance,
                "required_balance": required_balance,
                "has_sufficient": has_sufficient
            }
        )
        
        # Show result and appropriate next steps
        if has_sufficient:
            keyboard = InlineKeyboardMarkup([
                [build_button("💰 Fund Bundled Wallets", "fund_bundled_wallets_now")],
                [build_button("🔄 Check Balance Again", "check_wallet_balance")]
            ])
        else:
            keyboard = InlineKeyboardMarkup([
                [build_button("✏️ Reduce Buy Amounts", "edit_buy_amounts")],
                [build_button("🔄 Check Balance Again", "check_wallet_balance")],
                [build_button("« Back to Activities", "back_to_activities")]
            ])
        
        await query.edit_message_text(
            format_wallet_balance_result_message(airdrop_wallet, current_balance, required_balance, has_sufficient),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_BALANCE_CHECK if has_sufficient else ConversationState.BUY_AMOUNTS_PREVIEW
        
    except Exception as e:
        logger.error(
            f"Wallet balance check failed for user {user.id}: {str(e)}",
            extra={"user_id": user.id}
        )
        
        keyboard = InlineKeyboardMarkup([
            [build_button("Try Again", "check_wallet_balance")],
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await query.edit_message_text(
            format_pumpfun_error_message("balance_check", str(e)),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUY_AMOUNTS_PREVIEW


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
        airdrop_wallet = session_manager.get_session_value(user.id, "airdrop_wallet")
        
        if not all([pumpfun_client, bundled_wallets_count, airdrop_wallet]):
            raise Exception("Missing required session data for wallet funding")
        
        # Show funding requirement message
        keyboard = InlineKeyboardMarkup([
            [build_button("💰 Start Funding", "start_wallet_funding")],
            [build_button("« Back to Balance Check", "check_wallet_balance")]
        ])
        
        await query.edit_message_text(
            format_wallet_funding_required_message(airdrop_wallet, bundled_wallets_count),
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
        # Get required data from session
        pumpfun_client = session_manager.get_session_value(user.id, "pumpfun_client")
        bundled_wallets_count = session_manager.get_session_value(user.id, "bundled_wallets_count")
        
        if not all([pumpfun_client, bundled_wallets_count]):
            raise Exception("Missing required session data for wallet funding")
        
        # Show progress message
        await query.edit_message_text(
            format_wallet_funding_progress_message({
                "processed": 0,
                "total": bundled_wallets_count,
                "successful": 0,
                "failed": 0,
                "current_wallet": "Initializing..."
            }),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Calculate funding amount per wallet
        amount_per_wallet = 0.01  # 0.01 SOL per wallet
        
        # Execute funding using PumpFun API
        logger.info(f"Starting wallet funding for user {user.id}: {bundled_wallets_count} wallets, {amount_per_wallet} SOL each")
        funding_result = pumpfun_client.fund_bundled_wallets(amount_per_wallet)
        
        # Store funding results
        session_manager.update_session_value(user.id, "funding_results", funding_result)
        
        logger.info(
            f"Wallet funding completed for user {user.id}",
            extra={
                "user_id": user.id,
                "successful_transfers": funding_result.get("successful_transfers", 0),
                "failed_transfers": funding_result.get("failed_transfers", 0)
            }
        )
        
        # Show completion message and next steps
        failed_transfers = funding_result.get("failed_transfers", 0)
        
        if failed_transfers == 0:
            keyboard = InlineKeyboardMarkup([
                [build_button("🚀 Create Token & Buy", "create_token_final")],
                [build_button("📊 View Funding Details", "view_funding_details")]
            ])
        else:
            keyboard = InlineKeyboardMarkup([
                [build_button("🔄 Retry Failed Wallets", "retry_wallet_funding")],
                [build_button("🚀 Proceed with Funded Wallets", "create_token_final")],
                [build_button("📊 View Funding Details", "view_funding_details")]
            ])
        
        await query.edit_message_text(
            format_wallet_funding_complete_message(funding_result),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_FUNDING_PROGRESS
        
    except Exception as e:
        logger.error(
            f"Wallet funding failed for user {user.id}: {str(e)}",
            extra={"user_id": user.id}
        )
        
        keyboard = InlineKeyboardMarkup([
            [build_button("Try Again", "start_wallet_funding")],
            [build_button("« Back to Balance Check", "check_wallet_balance")]
        ])
        
        await query.edit_message_text(
            format_pumpfun_error_message("wallet_funding", str(e)),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_FUNDING_REQUIRED


async def create_token_final(update: Update, context: CallbackContext) -> int:
    """
    Create the token with configured buy amounts after all preparation is complete.
    
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
        token_params = session_manager.get_session_value(user.id, "token_params")
        buy_amounts = session_manager.get_session_value(user.id, "buy_amounts")
        
        if not all([pumpfun_client, token_params, buy_amounts]):
            raise Exception("Missing required session data for token creation")
        
        # Show progress message
        await query.edit_message_text(
            "🚀 **Creating Token with Initial Buys...**\n\n"
            "⏳ Creating your token and executing initial purchases with configured amounts...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Convert to the expected format for create_token_and_buy
        from bot.api.pumpfun_client import TokenCreationParams, BuyAmounts
        
        token_creation_params = TokenCreationParams(
            name=token_params["name"],
            symbol=token_params["ticker"],
            description=token_params["description"],
            image_url=token_params.get("image_url", "")
        )
        
        # Use the user-configured buy amounts
        buy_amounts_obj = BuyAmounts(
            dev_wallet_buy_sol=buy_amounts.get("DevWallet", 0.01),
            first_bundled_wallet_1_buy_sol=buy_amounts.get("First Bundled Wallet 1", 0.01),
            first_bundled_wallet_2_buy_sol=buy_amounts.get("First Bundled Wallet 2", 0.01),
            first_bundled_wallet_3_buy_sol=buy_amounts.get("First Bundled Wallet 3", 0.01),
            first_bundled_wallet_4_buy_sol=buy_amounts.get("First Bundled Wallet 4", 0.01)
        )
        
        logger.info(f"Creating final token with configured buy amounts for user {user.id}")
        start_time = time.time()
        
        # Create token and execute buys with user-configured amounts
        token_result = pumpfun_client.create_token_and_buy(
            token_params=token_creation_params,
            buy_amounts=buy_amounts_obj
        )
        
        execution_time = time.time() - start_time
        
        # Store final results
        session_manager.update_session_value(user.id, "token_address", token_result["token_address"])
        session_manager.update_session_value(user.id, "token_creation_signature", token_result["signature"])
        session_manager.update_session_value(user.id, "final_creation_results", token_result)
        
        logger.info(
            f"Final token creation completed for user {user.id}",
            extra={
                "user_id": user.id,
                "token_address": token_result["token_address"],
                "execution_time": execution_time
            }
        )
        
        # Show success results
        keyboard = InlineKeyboardMarkup([
            [build_button("🎉 Start New Bundle", "back_to_activities")],
            [build_button("📊 View Transaction Details", "view_final_details")]
        ])
        
        # Prepare results data for display
        results_with_token = {
            "operation_type": "token_creation_with_buys",
            "success": True,
            "token_address": token_result["token_address"],
            "total_operations": len(buy_amounts),
            "successful_operations": len(buy_amounts),  # Assume all successful for now
            "failed_operations": 0,
            "execution_time": execution_time,
            "buy_amounts": buy_amounts
        }
        
        await query.edit_message_text(
            format_bundle_operation_results(results_with_token),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.BUNDLE_OPERATION_COMPLETE
        
    except Exception as e:
        logger.error(
            f"Final token creation failed for user {user.id}: {str(e)}",
            extra={"user_id": user.id}
        )
        
        keyboard = InlineKeyboardMarkup([
            [build_button("Try Again", "create_token_final")],
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        await query.edit_message_text(
            format_pumpfun_error_message("final_token_creation", str(e)),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.WALLET_FUNDING_PROGRESS


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


async def start_buy_amounts_input(update: Update, context: CallbackContext) -> int:
    """
    Start the actual buy amounts input process.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Get wallet names from session
    wallet_names = session_manager.get_session_value(user.id, "buy_amounts_wallets")
    
    if not wallet_names:
        # Fallback if not in session
        wallet_names = ["DevWallet", "First Bundled Wallet 1", "First Bundled Wallet 2", 
                       "First Bundled Wallet 3", "First Bundled Wallet 4"]
        session_manager.update_session_value(user.id, "buy_amounts_wallets", wallet_names)
    
    # Reset to first wallet
    session_manager.update_session_value(user.id, "current_buy_wallet_index", 0)
    
    # Request first wallet buy amount
    keyboard = InlineKeyboardMarkup([
        [build_button("« Back to Activities", "back_to_activities")]
    ])
    
    await query.edit_message_text(
        format_buy_amount_request(wallet_names[0], 1, len(wallet_names)),
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.BUY_AMOUNTS_INPUT


async def back_to_token_preview(update: Update, context: CallbackContext) -> int:
    """
    Go back to token creation preview.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Get token params from session
    token_params = session_manager.get_session_value(user.id, "token_params") or {}
    
    # Show preview again
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