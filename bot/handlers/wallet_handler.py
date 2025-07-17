"""
This module handles all wallet-related operations for the bot,
including airdrop and bundled wallet management.
"""

from typing import Dict, List, Any, Optional
import asyncio
import time
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext
from loguru import logger
import base64
import base58
import os

from bot.config import ConversationState, CallbackPrefix
from bot.utils.keyboard_utils import build_button, build_keyboard
from bot.utils.message_utils import (
    format_pumpfun_error_message, 
    format_bundled_wallets_created_message,
    format_bundled_wallets_creation_message,
    format_existing_bundled_wallets_selected_message,
    format_wallet_balance_check_message,
    format_wallet_balance_result_message,
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
from bot.utils.validation_utils import validate_bundled_wallets_count, log_validation_result


def is_base58_private_key(private_key: str) -> bool:
    """
    Check if a private key is in base58 format.
    A simple check based on length and character set.
    """
    if not isinstance(private_key, str):
        return False
    
    # Base58 private keys are typically 64 characters long (for a 32-byte key)
    # or 88 characters for a 64-byte key. Let's check for a reasonable range.
    if not (60 <= len(private_key) <= 90):
        return False
    
    # Check if all characters are valid base58 characters
    base58_chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    return all(c in base58_chars for c in private_key)


def convert_base64_to_base58(base64_key: str) -> str:
    """
    Convert a base64 private key to base58 format.
    """
    try:
        # Decode from base64
        decoded_key = base64.b64decode(base64_key)
        
        # Encode to base58
        base58_key = base58.b58encode(decoded_key).decode('utf-8')
        
        return base58_key
    except (base64.binascii.Error, ValueError) as e:
        raise ValueError(f"Invalid base64 format: {e}")


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
        
        # Import wallet using PumpFun API (convert base64 to base58 if needed)
        logger.info(f"Importing airdrop wallet for user {user.id}")
        
        try:
            # Check if the private key is already in base58 format
            if is_base58_private_key(private_key):
                api_private_key = private_key
                logger.info(f"Private key already in base58 format")
            else:
                # Convert from base64 to base58 format
                api_private_key = convert_base64_to_base58(private_key)
                logger.info(f"Successfully converted private key from base64 to base58 (length: {len(private_key)} -> {len(api_private_key)})")
            
            wallet_info = pumpfun_client.create_airdrop_wallet(api_private_key)
        except ValueError as conv_error:
            logger.error(f"Failed to convert private key format: {conv_error}")
            raise Exception(f"Invalid private key format: {conv_error}")
        
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
            f"Please enter a number between 2 and 50:",
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
    
    # CRITICAL FIX: Use same increased funding amounts as funding function for consistency
    # DevWallet: 0.055 base + buy_amount + 0.002 buffer = more margin for gas fees
    dev_wallet_required = 0.055 + dev_wallet_buy_amount + 0.002
    # Bundled wallets: 0.025 base + buy_amount + 0.002 buffer = ensures >10,000 lamports usable
    bundled_wallet_required = 0.025 + first_bundled_buy_amount + 0.002
    
    # CRITICAL DEBUGGING: Log addresses being checked for balance consistency tracking
    airdrop_wallet_address = session_manager.get_session_value(user.id, "airdrop_wallet_address")
    logger.info(f"BALANCE CHECK DEBUG: Using airdrop wallet address: {airdrop_wallet_address}")
    logger.info(f"BALANCE CHECK DEBUG: Dev wallet required: {dev_wallet_required:.6f} SOL")
    logger.info(f"BALANCE CHECK DEBUG: Bundled wallet required: {bundled_wallet_required:.6f} SOL")
    
    await query.edit_message_text("🔍 **Checking Bundled Wallet Balances**...", parse_mode=ParseMode.MARKDOWN)
    
    # STEP 1: Check bundled wallets first
    try:
        if not airdrop_wallet_address:
            raise Exception("Airdrop wallet address not found in session")
        
        # CRITICAL FIX: Use same data source as funding process for consistency
        # Load bundled wallet data from session first (same as funding process)
        bundled_wallets_data = session_manager.get_session_value(user.id, "bundled_wallets_data")
        bundled_wallets_original_json = session_manager.get_session_value(user.id, "bundled_wallets_original_json")
        
        # Use storage as fallback if session data is not available
        if not bundled_wallets_data and not bundled_wallets_original_json:
            logger.info("No bundled wallet data in session, loading from storage as fallback")
            bundled_wallets_data = bundled_wallet_storage.load_bundled_wallets(airdrop_wallet_address, user.id)
        else:
            logger.info("Using bundled wallet data from session for consistency with funding process")
            
            # Extract wallet list from session data structure (same logic as funding)
            if bundled_wallets_original_json and isinstance(bundled_wallets_original_json, dict) and "data" in bundled_wallets_original_json:
                bundled_wallets_data = bundled_wallets_original_json["data"]
                logger.info("Using original JSON data format from session")
            elif bundled_wallets_data and isinstance(bundled_wallets_data, list):
                logger.info("Using normalized data format from session")
            else:
                logger.warning("Session data format unexpected, falling back to storage")
                bundled_wallets_data = bundled_wallet_storage.load_bundled_wallets(airdrop_wallet_address, user.id)
        
        if not bundled_wallets_data:
            raise Exception(f"No bundled wallets found for user {user.id} with airdrop wallet {airdrop_wallet_address[:8]}...")
        
        funded_count = 0
        total_wallets = len(bundled_wallets_data)
        insufficient_wallets = []
        
        logger.info(f"Checking SOL balance for {total_wallets} bundled wallets with API requirements")
        
        # CRITICAL DEBUGGING: Log all wallet addresses being checked for balance
        for idx, wallet in enumerate(bundled_wallets_data):
            wallet_address = wallet.get("address") or wallet.get("publicKey")
            wallet_name = wallet.get("name", f"wallet_{idx}")
            logger.info(f"BALANCE CHECK DEBUG: Will check {wallet_name} address: {wallet_address}")
        
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
        
        # Import message formatter dynamically
        from bot.utils.message_utils import format_wallet_funding_required_message
        
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
        
        # Import required dynamic message utilities
        from bot.utils.message_utils import (
            format_wallet_funding_progress_message,
            format_wallet_funding_complete_message
        )
        
        # Import wallet funding to API first (ensure bundled wallets are accessible)
        airdrop_private_key = session_manager.get_session_value(user.id, "airdrop_private_key")
        if airdrop_private_key:
            try:
                # Convert private key format if needed (same as import function)
                if is_base58_private_key(airdrop_private_key):
                    api_airdrop_key = airdrop_private_key
                    logger.info(f"Airdrop private key already in base58 format")
                else:
                    # Convert from base64 to base58 format
                    api_airdrop_key = convert_base64_to_base58(airdrop_private_key)
                    logger.info(f"Successfully converted airdrop private key from base64 to base58")
                
                pumpfun_client.create_airdrop_wallet(api_airdrop_key)
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
                    
                    # CRITICAL DEBUGGING: Log wallet addresses for consistency verification  
                    wallet_validation_passed = True
                    for idx, wallet in enumerate(wallets_to_import):
                        wallet_addr = wallet.get("publicKey", "unknown") if isinstance(wallet, dict) else "unknown"
                        wallet_name = wallet.get("name", f"wallet_{idx}") if isinstance(wallet, dict) else f"wallet_{idx}"
                        private_key = wallet.get("privateKey", "") if isinstance(wallet, dict) else ""
                        
                        logger.info(f"FUNDING IMPORT DEBUG: {wallet_name} address: {wallet_addr}")
                        
                        # CRITICAL FIX: Validate wallet data format before API import
                        if not wallet_addr or wallet_addr == "unknown":
                            logger.error(f"Invalid wallet address for {wallet_name}: {wallet_addr}")
                            wallet_validation_passed = False
                        if not private_key:
                            logger.error(f"Missing private key for {wallet_name}")
                            wallet_validation_passed = False
                        elif len(private_key) < 40:  # Basic sanity check for key length
                            logger.error(f"Private key too short for {wallet_name}: {len(private_key)} chars")
                            wallet_validation_passed = False
                    
                    if not wallet_validation_passed:
                        raise Exception("Wallet data validation failed - invalid addresses or missing private keys")
                    
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
                                # CRITICAL FIX: Convert private key to base58 format if needed (fixes Non-base58 character error)
                                if is_base58_private_key(private_key):
                                    private_key_bs58 = private_key
                                    logger.info(f"DEBUG: Wallet '{name}' already in base58 format")
                                else:
                                    private_key_bs58 = convert_base64_to_base58(private_key)
                                    logger.info(f"DEBUG: Converted wallet '{name}' from base64 to base58 format")
                                
                                api_wallets.append({
                                    "name": name,
                                    "privateKey": private_key_bs58
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
        
        # CRITICAL FIX: Increase funding amounts to ensure sufficient balance
        # Based on cause_debugging.yaml - increase from 0.003 to 0.005 SOL per wallet minimum
        # DevWallet: 0.055 base + buy_amount + 0.002 buffer = more margin for gas fees
        dev_wallet_required = 0.055 + dev_wallet_buy_amount + 0.002
        # Bundled wallets: 0.025 base + buy_amount + 0.002 buffer = ensures >10,000 lamports usable
        bundled_wallet_required = 0.025 + first_bundled_buy_amount + 0.002
        
        # CRITICAL DEBUGGING: Log wallet addresses being used for funding to ensure consistency
        logger.info(f"FUNDING DEBUG: Using airdrop wallet address: {airdrop_wallet}")
        logger.info(f"FUNDING DEBUG: Dev wallet required: {dev_wallet_required:.6f} SOL")
        logger.info(f"FUNDING DEBUG: Bundled wallet required: {bundled_wallet_required:.6f} SOL")
        
        # CRITICAL FIX: Prepare funding data according to API documentation format
        # API expects: amountPerWalletSOL, childWallets, motherWalletPrivateKeyBs58
        
        # Build childWallets array with private keys from session data
        child_wallets = []
        
        # Get airdrop private key for mother wallet
        airdrop_private_key = session_manager.get_session_value(user.id, "airdrop_private_key")
        if not airdrop_private_key:
            raise Exception("Airdrop private key not found in session")
        
        # Convert airdrop private key to base58 if needed
        if is_base58_private_key(airdrop_private_key):
            mother_wallet_key = airdrop_private_key
        else:
            mother_wallet_key = convert_base64_to_base58(airdrop_private_key)
        
        # Use the same wallet data source as the import process for consistency
        if bundled_wallets_original_json and isinstance(bundled_wallets_original_json, dict) and "data" in bundled_wallets_original_json:
            wallet_data_list = bundled_wallets_original_json["data"]
        elif bundled_wallets_data and isinstance(bundled_wallets_data, list):
            wallet_data_list = bundled_wallets_data
        else:
            # Fallback to storage
            wallet_data_list = bundled_wallet_storage.load_bundled_wallets(airdrop_wallet, user.id)
        
        # Build childWallets array with proper API format
        for wallet in wallet_data_list:
            wallet_name = wallet.get("name", "Unknown")
            wallet_private_key = wallet.get("privateKey") or wallet.get("private_key")
            
            if wallet_private_key:
                # Convert to base58 if needed
                if is_base58_private_key(wallet_private_key):
                    api_private_key = wallet_private_key
                else:
                    api_private_key = convert_base64_to_base58(wallet_private_key)
                
                child_wallets.append({
                    "name": wallet_name,
                    "privateKey": api_private_key
                })
        
        if not child_wallets:
            raise Exception("No valid child wallets found for funding")
        
        logger.info(f"Prepared {len(child_wallets)} child wallets for funding")
        
        # Determine which wallet to fund based on requirements
        # Fund DevWallet and First Bundled Wallet 1 with their respective amounts
        target_wallet_names = ["DevWallet", "First Bundled Wallet 1"]
        
        # CRITICAL FIX: Use DevWallet amount for all since the API uses amountPerWalletSOL
        # The API will use the same amount for all wallets, so we need to use the higher amount
        # to ensure all wallets get sufficient funding
        funding_amount_sol = dev_wallet_required
        
        logger.info(f"Funding {len(target_wallet_names)} wallets with {funding_amount_sol:.6f} SOL each")
        logger.info(f"Target wallets: {target_wallet_names}")
        logger.info(f"Child wallets prepared: {[w['name'] for w in child_wallets]}")
        
        # Execute funding operation with correct API format according to bundler_api.md
        logger.info(f"Executing wallet funding for user {user.id}")
        
        # CRITICAL FIX: Use correct method signature from working code
        try:
            logger.info(f"Calling fund_bundled_wallets with:")
            logger.info(f"  - amount_per_wallet: {funding_amount_sol}")
            logger.info(f"  - bundled_wallets count: {len(child_wallets)}")
            logger.info(f"  - mother_private_key: [REDACTED]")
            logger.info(f"  - target_wallet_names: {target_wallet_names}")
            
            funding_results = pumpfun_client.fund_bundled_wallets(
                amount_per_wallet=funding_amount_sol,
                mother_private_key=mother_wallet_key,
                bundled_wallets=child_wallets,
                target_wallet_names=target_wallet_names
            )
            logger.info(f"Successfully funded wallets using correct method signature")
            logger.info(f"Funding results: {funding_results}")
        except TypeError as param_error:
            if "unexpected keyword argument" in str(param_error):
                logger.warning(f"Method signature still has issues, trying alternative call patterns: {param_error}")
                
                # Try alternative parameter names for backward compatibility
                try:
                    # Alternative 1: Positional arguments in correct order
                    funding_results = pumpfun_client.fund_bundled_wallets(
                        funding_amount_sol, mother_wallet_key, child_wallets, target_wallet_names
                    )
                    logger.info("Successfully used positional arguments")
                except TypeError:
                    try:
                        # Alternative 2: Mixed approach with explicit parameters
                        funding_results = pumpfun_client.fund_bundled_wallets(
                            funding_amount_sol, 
                            mother_private_key=mother_wallet_key,
                            bundled_wallets=child_wallets,
                            target_wallet_names=target_wallet_names
                        )
                        logger.info("Successfully used mixed parameter approach")
                    except Exception as mixed_error:
                        logger.error(f"All funding call formats failed. Original: {param_error}, Positional: Failed, Mixed: {mixed_error}")
                        raise param_error
            else:
                raise param_error
        
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
        
        # Enhanced error handling logic
        error_msg = str(e).lower()
        
        # Check for specific error types
        is_prerequisite_error = any(keyword in error_msg 
                                   for keyword in ["not found", "missing", "session", "pumpfun client"])
        is_validation_error = any(keyword in error_msg 
                                 for keyword in ["validation", "invalid", "format", "bs58", "private key"])
        
        # Specific check for wallet-related errors
        is_wallet_error = any(keyword in error_msg 
                             for keyword in ["wallet", "bundled wallets", "airdrop wallet"])
        
        if is_prerequisite_error or is_wallet_error:
            # Missing prerequisites - suggest restart
            keyboard = InlineKeyboardMarkup([
                [build_button("🔄 Restart Setup", "back_to_activities")],
                [build_button("📋 Check Prerequisites", "check_wallet_balance")]
            ])
            
            error_message = (
                "❌ **Setup Prerequisites Missing**\n\n"
                f"The wallet funding process failed because some required setup is missing:\n\n"
                f"**Error:** {str(e)}\n\n"
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
                f"**Error:** {str(e)}\n\n"
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
            airdrop_wallet_address = session_manager.get_session_value(user.id, "airdrop_wallet_address")
            if airdrop_wallet_address:
                bundled_wallets_from_storage = bundled_wallet_storage.load_bundled_wallets(airdrop_wallet_address, user.id)
                if bundled_wallets_from_storage:
                    bundled_wallets_original_json = {"data": bundled_wallets_from_storage}
        
        if bundled_wallets_original_json:
            # Extract wallets from data structure
            wallets_to_process = []
            if isinstance(bundled_wallets_original_json, list):
                wallets_to_process = bundled_wallets_original_json
            elif isinstance(bundled_wallets_original_json, dict) and "data" in bundled_wallets_original_json:
                wallets_to_process = bundled_wallets_original_json["data"]
            elif isinstance(bundled_wallets_original_json, dict) and "wallets" in bundled_wallets_original_json:
                wallets_to_process = bundled_wallets_original_json["wallets"]
            
            for wallet in wallets_to_process:
                if isinstance(wallet, dict):
                    private_key = wallet.get("privateKey") or wallet.get("private_key") or wallet.get("privateKeyBs58")
                    name = wallet.get("name", "Unknown")
                    
                    if private_key:
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
        import json
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
                    [build_button("🔄 Wait & Retry", "wait_and_retry_airdrop")],
                    [build_button("« Back to Balance Check", "check_wallet_balance")]
                ])
                
                error_title = "**Server Configuration Error**"
                error_context = "The API server has a configuration issue that prevents the return funds operation."
                
            elif "timeout" in error_message or "connection" in error_message:
                keyboard = InlineKeyboardMarkup([
                    [build_button("🔄 Try Again", "execute_return_funds")],
                    [build_button("⏱️ Wait & Retry", "wait_and_retry_airdrop")],
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
            # Proceed to token creation - defer to avoid circular import
            logger.info(f"User {user.id} chose to proceed to token creation from return funds complete")
            # Return the appropriate state that will route to token creation
            return ConversationState.TOKEN_CREATION_PREVIEW
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


