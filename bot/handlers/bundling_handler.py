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
import os
import glob
import json


def load_bundled_wallets_from_storage() -> List[Dict[str, Any]]:
    """
    Load bundled wallet data from local JSON files.
    
    Returns:
        List of wallet dictionaries with publicKey, privateKey, and name
    """
    try:
        # Get the bundled wallets directory
        bundled_wallets_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "bundled_wallets")
        
        # Find all bundled wallet JSON files
        json_files = glob.glob(os.path.join(bundled_wallets_dir, "bundled_*.json"))
        
        if not json_files:
            logger.warning("No bundled wallet JSON files found in storage")
            return []
        
        # Load the most recent bundled wallet file (by timestamp)
        latest_file = max(json_files, key=os.path.getctime)
        logger.info(f"Loading bundled wallets from: {latest_file}")
        
        with open(latest_file, 'r') as f:
            wallet_data = json.load(f)
        
        # Extract the wallet data array
        wallets = wallet_data.get("data", [])
        
        if not wallets:
            logger.warning("No wallet data found in bundled wallet file")
            return []
        
        logger.info(f"Loaded {len(wallets)} bundled wallets from storage")
        return wallets
        
    except Exception as e:
        logger.error(f"Error loading bundled wallets from storage: {e}")
        return []


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
        session_manager.update_session_value(user.id, "airdrop_wallet_address", wallet_info["address"])
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
        session_manager.update_session_value(user.id, "airdrop_wallet_address", wallet_info["address"])
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
        airdrop_wallet_address = session_manager.get_session_value(user.id, "airdrop_wallet_address")
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
            
            # CRITICAL FIX: Also load and store the original JSON file data for API import
            # The load_bundled_wallets() normalizes the data, but we need the original privateKey format
            try:
                original_json_data = bundled_wallet_storage.get_bundled_wallets_by_airdrop(user.id, airdrop_wallet_address)
                if original_json_data:
                    session_manager.update_session_value(user.id, "bundled_wallets_original_json", original_json_data)
                    logger.info(f"Stored original JSON data for API import for user {user.id}")
                else:
                    logger.warning(f"Could not load original JSON data for user {user.id}")
            except Exception as json_load_error:
                logger.warning(f"Failed to load original JSON data: {str(json_load_error)}")
            
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
            airdrop_wallet_address = session_manager.get_session_value(user.id, "airdrop_wallet_address")
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
    parameter_order = ["name", "ticker", "description", "image_url"]
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
            "image_url": "the URL of your token's image/logo (optional)"
        }
        
        await update.message.reply_text(
            format_token_parameter_request(next_param, param_descriptions.get(next_param, "this parameter")),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.TOKEN_PARAMETER_INPUT
    else:
        # All parameters collected, add standard supply and show preview
        token_params["initial_supply"] = 1000000000  # Standard supply
        session_manager.update_session_value(user.id, "token_params", token_params)
        
        # Get bundled wallets count for the buy amounts config
        bundled_wallets_count = session_manager.get_session_value(user.id, "bundled_wallets_count", 0)
        
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
    
    # Get total bundled wallets count from session
    bundled_wallets_count = session_manager.get_session_value(user.id, "bundled_wallets_count", 0)
    
    # Initialize buy amounts configuration for wallet groups
    wallet_groups = ["DevWallet"]
    
    if bundled_wallets_count > 0:
        # Always add first bundled wallets group (up to 4 wallets)
        first_four_count = min(4, bundled_wallets_count)
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
        "First Bundled Wallets": "Primary trading wallets (First Bundled Wallet 1-4)",
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
            "First Bundled Wallets": "Primary trading wallets (First Bundled Wallet 1-4)",
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
    
    # Calculate total funding needed per bundled wallet
    total_per_wallet = sum([
        buy_amounts.get("first_bundled_wallet_1_buy_sol", 0),
        buy_amounts.get("first_bundled_wallet_2_buy_sol", 0), 
        buy_amounts.get("first_bundled_wallet_3_buy_sol", 0),
        buy_amounts.get("first_bundled_wallet_4_buy_sol", 0)
    ]) / 4.0  # Average amount per wallet
    
    # Add buffer for transaction fees (0.002 SOL per wallet)
    required_per_wallet = total_per_wallet + 0.002
    
    await query.edit_message_text("🔍 **Checking Bundled Wallet Balances**...", parse_mode=ParseMode.MARKDOWN)
    
    # STEP 1: Check bundled wallets first
    try:
        bundled_wallets_status = await check_bundled_wallets_funding_status(
            pumpfun_client, bundled_wallets_count, required_per_wallet
        )
        
        if bundled_wallets_status.get("all_funded", False):
            # All bundled wallets have sufficient funds
            await context.bot.send_message(
                chat_id=user.id,
                text=f"✅ **All Bundled Wallets Ready**\n\n"
                     f"All {bundled_wallets_count} bundled wallets have sufficient SOL "
                     f"({required_per_wallet:.4f} SOL each required).\n\n"
                     f"Ready to proceed with token creation!",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [build_button("🚀 Create Token", "create_token_final")],
                    [build_button("📝 Edit Buy Amounts", "edit_buy_amounts")]
                ])
            )
            return ConversationState.WALLET_FUNDING_PROGRESS
        
        # Some bundled wallets need funding
        funded_count = bundled_wallets_status.get("funded_count", 0)
        total_funding_needed = (bundled_wallets_count - funded_count) * required_per_wallet
        
        await context.bot.send_message(
            chat_id=user.id,
            text=f"⚠️ **Bundled Wallets Need Funding**\n\n"
                 f"Ready wallets: {funded_count}/{bundled_wallets_count}\n"
                 f"Total funding needed: {total_funding_needed:.4f} SOL\n\n"
                 f"Checking airdrop wallet balance...",
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
        total_funding_needed = bundled_wallets_count * required_per_wallet
    
    # STEP 2: Check airdrop wallet balance
    try:
        airdrop_wallet_address = session_manager.get_session_value(user.id, "airdrop_wallet_address")
        if not airdrop_wallet_address:
            raise Exception("Airdrop wallet address not found in session")
        
        balance_response = pumpfun_client.get_wallet_balance(airdrop_wallet_address)
        current_balance = balance_response.get("data", {}).get("balance", 0)
        
        # Add buffer for transaction fees
        total_needed_with_buffer = total_funding_needed + 0.01  # Extra buffer for fees
        
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
                     f"Please fund your airdrop wallet with at least {shortfall:.4f} SOL.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
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
        
        logger.info(
            f"Starting wallet funding validation for user {user.id}",
            extra={
                "user_id": user.id,
                "airdrop_wallet": airdrop_wallet,
                "bundled_wallets_count": bundled_wallets_count,
                "bundled_wallets_addresses": bundled_wallets[:3] if bundled_wallets else []  # Log first 3 for reference
            }
        )
        
        # Show progress message
        await query.edit_message_text(
            format_wallet_funding_progress_message({
                "processed": 0,
                "total": bundled_wallets_count,
                "successful": 0,
                "failed": 0,
                "current_wallet": "Initializing and validating prerequisites..."
            }),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Ensure airdrop wallet is imported to API before funding
        airdrop_private_key = session_manager.get_session_value(user.id, "airdrop_private_key")
        if airdrop_private_key:
            try:
                logger.info(f"Importing airdrop wallet to API for user {user.id}")
                await query.edit_message_text(
                    format_wallet_funding_progress_message({
                        "processed": 0,
                        "total": bundled_wallets_count,
                        "successful": 0,
                        "failed": 0,
                        "current_wallet": "Importing airdrop wallet to API..."
                    }),
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Import airdrop wallet to API
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
                    
                    # Format bundled wallets for API import (name and privateKey fields)
                    api_wallets = []
                    for i, wallet in enumerate(wallets_to_import):
                        if isinstance(wallet, dict):
                            # Handle different key formats (privateKey vs private_key)
                            private_key = wallet.get("privateKey") or wallet.get("private_key")
                            name = wallet.get("name", f"Wallet_{len(api_wallets) + 1}")
                            
                            logger.info(f"DEBUG: Processing wallet {i}: name='{name}', has_privateKey={bool(wallet.get('privateKey'))}, has_private_key={bool(wallet.get('private_key'))}")
                            
                            if private_key:
                                api_wallets.append({
                                    "name": name,
                                    "privateKey": private_key
                                })
                                logger.info(f"DEBUG: Added wallet '{name}' to API import list")
                            else:
                                logger.warning(f"Bundled wallet missing private key, skipping: {wallet.get('name', 'Unknown')}")
                                logger.warning(f"DEBUG: Wallet {i} keys: {list(wallet.keys())}")
                    
                    logger.info(f"DEBUG: Prepared {len(api_wallets)} wallets for API import")
                    
                    if api_wallets:
                        # DEBUG: Log what we're about to send to API
                        logger.info(f"DEBUG: Sending {len(api_wallets)} wallets to API import")
                        for i, api_wallet in enumerate(api_wallets):
                            logger.info(f"DEBUG: API wallet {i}: name='{api_wallet['name']}', privateKey_length={len(api_wallet['privateKey']) if api_wallet.get('privateKey') else 0}")
                        
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
                            api_import_success = False
                            # Store the error for later decision making
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
                            # UI errors should not stop the process
                            logger.warning(f"UI update failed but API operation status: {api_import_success}, continuing: {ui_error}")
                        
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
                            except Exception:
                                pass  # Ignore UI errors during recovery
                            
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
                        
                        elif not wallets_verified and api_import_success:
                            # Import seemed to succeed but verification failed - log warning but continue
                            logger.warning("Import reported success but verification failed - proceeding with caution")
                            
                        elif wallets_verified:
                            logger.info("✅ Bundled wallets verified successfully on API server")
                            
                    else:
                        logger.warning(f"No valid bundled wallets found to import for user {user.id}")
                        logger.warning(f"DEBUG: Original wallets_to_import count: {len(wallets_to_import)}")
                        for i, wallet in enumerate(wallets_to_import):
                            logger.warning(f"DEBUG: Original wallet {i}: {wallet}")
                        
                        # No wallets to import is a critical error
                        raise Exception("No valid bundled wallets found for import - check wallet data format")
                        
                else:
                    logger.warning(f"No wallets found in bundled_wallets_data for user {user.id}")
                    logger.warning(f"DEBUG: wallets_to_import: {wallets_to_import}")
                    
                    # No wallet data is a critical error  
                    raise Exception("No bundled wallet data found - please create bundled wallets first")
                
            except Exception as import_error:
                logger.error(f"Failed to import bundled wallets to API: {str(import_error)}")
                logger.error(f"DEBUG: Import process error type: {type(import_error)}")
                logger.error(f"DEBUG: Import process error details: {repr(import_error)}")
                
                # PHASE 2 FIX: Don't continue with funding if import failed
                # Instead, provide specific error handling and recovery options
                
                error_msg = str(import_error)
                if "no valid bundled wallets" in error_msg.lower():
                    keyboard = InlineKeyboardMarkup([
                        [build_button("🔄 Recreate Bundled Wallets", "retry_bundled_wallets")],
                        [build_button("📋 Check Wallet Data", "debug_wallet_data")],
                        [build_button("« Back to Setup", "back_to_activities")]
                    ])
                    
                    error_response = (
                        "❌ **Bundled Wallet Import Failed**\n\n"
                        "No valid bundled wallets were found for import to the API.\n\n"
                        "**Possible causes:**\n"
                        "• Wallet data files are corrupted or missing\n"
                        "• Private keys are not in the expected format\n"
                        "• Wallet creation process was incomplete\n\n"
                        "**Recommended action:** Recreate bundled wallets from scratch."
                    )
                else:
                    keyboard = InlineKeyboardMarkup([
                        [build_button("🔄 Retry Import", "retry_wallet_import")],
                        [build_button("📊 Check API Status", "check_api_status")],
                        [build_button("« Back to Balance Check", "check_wallet_balance")]
                    ])
                    
                    error_response = (
                        "❌ **Wallet Import Process Failed**\n\n"
                        f"The bundled wallet import to the API failed:\n\n"
                        f"**Error:** {error_msg}\n\n"
                        "**Next Steps:**\n"
                        "1. Try importing again (temporary API issue)\n"
                        "2. Check API service status\n"
                        "3. Return to balance check and restart process\n\n"
                        "The funding process cannot continue without successful wallet import."
                    )
                
                await query.edit_message_text(
                    error_response,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
                
                return ConversationState.WALLET_FUNDING_REQUIRED
                
        else:
            logger.warning(f"No bundled wallets data found for user {user.id}, proceeding without import")
            logger.warning(f"DEBUG: bundled_wallets_data: {bundled_wallets_data}")
            logger.warning(f"DEBUG: bundled_wallets_original_json: {bundled_wallets_original_json}")
            logger.warning(f"DEBUG: Session keys for user {user.id}: {list(session_manager.get_session_data(user.id).keys()) if hasattr(session_manager, 'get_session_data') else 'Cannot get session keys'}")
            
            # No wallet data found is a critical error - don't continue
            keyboard = InlineKeyboardMarkup([
                [build_button("🔄 Create Bundled Wallets", "back_to_bundled_setup")],
                [build_button("« Back to Activities", "back_to_activities")]
            ])
            
            await query.edit_message_text(
                "❌ **No Bundled Wallets Found**\n\n"
                "No bundled wallet data was found in your session.\n\n"
                "**Required Action:** Create bundled wallets before attempting to fund them.\n\n"
                "Click 'Create Bundled Wallets' to set up your wallets first.",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.BUNDLED_WALLETS_COUNT
        
    except Exception as e:
        logger.error(
            f"Wallet funding failed for user {user.id}: {str(e)}",
            extra={"user_id": user.id},
            exc_info=True
        )
        
        # Enhanced error handling with specific guidance
        error_msg = str(e)
        is_validation_error = "validation" in error_msg.lower()
        is_prerequisite_error = any(keyword in error_msg.lower() for keyword in 
                                   ["not found", "missing", "airdrop wallet", "bundled wallets"])
        
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


async def create_token_final(update: Update, context: CallbackContext) -> int:
    """
    Create the token with configured buy amounts after all preparation is complete.
    Now handles the new wallet group structure.
    
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
        wallet_group_counts = session_manager.get_session_value(user.id, "wallet_group_counts", {})
        
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
        
        # Convert wallet group amounts to individual wallet amounts
        dev_wallet_amount = buy_amounts.get("DevWallet", 0.01)
        first_bundled_amount = buy_amounts.get("First Bundled Wallets", 0.01)
        
        # Use the wallet group amounts for the first 4 bundled wallets
        buy_amounts_obj = BuyAmounts(
            dev_wallet_buy_sol=dev_wallet_amount,
            first_bundled_wallet_1_buy_sol=first_bundled_amount,
            first_bundled_wallet_2_buy_sol=first_bundled_amount,
            first_bundled_wallet_3_buy_sol=first_bundled_amount,
            first_bundled_wallet_4_buy_sol=first_bundled_amount
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
        session_manager.update_session_value(user.id, "token_address", token_result["mint_address"])
        session_manager.update_session_value(user.id, "token_creation_signature", token_result.get("bundle_id", ""))
        session_manager.update_session_value(user.id, "final_creation_results", token_result)
        
        # Execute additional buys for remaining child wallets if configured
        additional_child_amount = buy_amounts.get("Additional Child Wallets")
        if additional_child_amount and additional_child_amount > 0:
            additional_count = wallet_group_counts.get("Additional Child Wallets", 0)
            if additional_count > 0:
                logger.info(f"Executing additional buys for {additional_count} remaining child wallets")
                try:
                    # Execute batch buy for remaining wallets
                    additional_result = pumpfun_client.batch_buy_token(
                        mint_address=token_result["mint_address"],
                        sol_amount_per_wallet=additional_child_amount,
                        slippage_bps=2500
                    )
                    logger.info(f"Additional buys completed: {additional_result}")
                except Exception as additional_error:
                    logger.warning(f"Additional buys failed: {str(additional_error)}")
        
        logger.info(
            f"Final token creation completed for user {user.id}",
            extra={
                "user_id": user.id,
                "token_address": token_result["mint_address"],
                "execution_time": execution_time
            }
        )
        
        # Show success results
        keyboard = InlineKeyboardMarkup([
            [build_button("🎉 Start New Bundle", "back_to_activities")],
            [build_button("📊 View Transaction Details", "view_final_details")]
        ])
        
        # Calculate total participating wallets
        total_participating_wallets = sum(wallet_group_counts.values())
        
        # Prepare results data for display
        results_with_token = {
            "operation_type": "token_creation_with_buys",
            "success": True,
            "token_address": token_result["mint_address"],
            "total_operations": total_participating_wallets,
            "successful_operations": total_participating_wallets,  # Assume all successful for now
            "failed_operations": 0,
            "execution_time": execution_time,
            "buy_amounts": buy_amounts,
            "wallet_group_counts": wallet_group_counts
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
            status_message += "1. Create bundled wallets (5-50 wallets recommended)\n"
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

async def check_bundled_wallets_funding_status(pumpfun_client, bundled_wallets_count: int, required_per_wallet: float) -> Dict[str, Any]:
    """
    Check if bundled wallets have sufficient funding by checking individual wallet balances.
    
    Args:
        pumpfun_client: PumpFun client instance
        bundled_wallets_count: Number of bundled wallets
        required_per_wallet: Required SOL per wallet
        
    Returns:
        Dictionary with funding status
    """
    try:
        # Load bundled wallet data from local storage
        bundled_wallets_data = load_bundled_wallets_from_storage()
        
        if not bundled_wallets_data:
            return {
                "all_funded": False,
                "funded_count": 0,
                "error": "No bundled wallets found in local storage"
            }
        
        funded_count = 0
        total_wallets = len(bundled_wallets_data)
        balance_check_errors = []
        
        logger.info(f"Checking SOL balance for {total_wallets} bundled wallets")
        
        # Check each wallet's SOL balance using enhanced API endpoint
        for wallet in bundled_wallets_data:
            wallet_address = wallet.get("publicKey")
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
                
                logger.info(f"Wallet {wallet_name} ({wallet_address[:8]}...): {sol_balance:.6f} SOL")
                
                if sol_balance >= required_per_wallet:
                    funded_count += 1
                    
            except Exception as e:
                logger.error(f"Error checking balance for wallet {wallet_name}: {e}")
                balance_check_errors.append(f"{wallet_name}: {str(e)}")
        
        all_funded = funded_count == total_wallets
        
        logger.info(f"Bundled wallet funding status: {funded_count}/{total_wallets} wallets funded")
        
        return {
            "all_funded": all_funded,
            "funded_count": funded_count,
            "total_wallets": total_wallets,
            "required_per_wallet": required_per_wallet,
            "balance_check_errors": balance_check_errors if balance_check_errors else None
        }
        
    except Exception as e:
        logger.error(f"Error checking bundled wallets funding status: {e}")
        return {
            "all_funded": False,
            "funded_count": 0,
            "error": str(e)
        }