"""
Token Creation Handler Module

This module contains all the handlers for the final token creation and preview logic,
including the token preview display and final token creation with buy execution.
"""

from typing import Dict, List, Any, Optional
import asyncio
import time
import re
import os
import json
import base64
import base58
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext
from loguru import logger

from bot.config import ConversationState, CallbackPrefix
from bot.state.session_manager import session_manager
from bot.utils.keyboard_utils import build_button, build_keyboard
from bot.utils.message_utils import (
    format_token_creation_preview,
    format_bundle_operation_results,
    format_pumpfun_error_message
)
from bot.utils.token_storage import token_storage


def is_base58_private_key(key: str) -> bool:
    """
    Check if a string is a valid base58 encoded Solana private key.
    
    Args:
        key: The key string to validate
        
    Returns:
        True if the key is valid base58 format, False otherwise
    """
    try:
        # Solana private keys in base58 format are typically 88 characters
        if len(key) != 88:
            return False
        
        # Try to decode as base58 - this will fail if not valid base58
        decoded = base58.b58decode(key)
        
        # Solana private keys should decode to 64 bytes
        if len(decoded) != 64:
            return False
            
        return True
    except Exception:
        return False


def convert_base64_to_base58(base64_key: str) -> str:
    """
    Convert a base64 encoded private key to base58 format.
    
    Args:
        base64_key: Base64 encoded private key
        
    Returns:
        Base58 encoded private key
    """
    try:
        # Decode base64 to bytes
        key_bytes = base64.b64decode(base64_key)
        
        # Validate that we have 64 bytes (Solana private key size)
        if len(key_bytes) != 64:
            raise ValueError(f"Invalid private key length: expected 64 bytes, got {len(key_bytes)}")
        
        # Encode to base58
        base58_key = base58.b58encode(key_bytes).decode('utf-8')
        return base58_key
    except Exception as e:
        logger.error(f"Failed to convert base64 to base58: {e}")
        raise ValueError(f"Invalid base64 private key: {e}")


def load_wallet_credentials_from_bundled_file(user_id: int) -> List[Dict[str, str]]:
    """
    Load wallet credentials from the bundled wallet file and convert to API format.
    
    Args:
        user_id: User ID to find the bundled wallet file
        
    Returns:
        List of wallet dictionaries with name and privateKey in base58 format
    """
    try:
        # Find the bundled wallet file for this user
        bundled_wallets_dir = os.path.join("ninjabot", "data", "bundled_wallets")
        if not os.path.exists(bundled_wallets_dir):
            bundled_wallets_dir = os.path.join("data", "bundled_wallets")
        
        # Find the file for this user
        bundled_file_path = None
        if os.path.exists(bundled_wallets_dir):
            # Find all files for this user and select the most recent one
            user_files = []
            for filename in os.listdir(bundled_wallets_dir):
                if filename.startswith(f"bundled_{user_id}_") and filename.endswith(".json"):
                    # Extract timestamp from filename
                    try:
                        timestamp_str = filename.split('_')[2]  # bundled_userid_timestamp_hash.json
                        timestamp = int(timestamp_str)
                        full_path = os.path.join(bundled_wallets_dir, filename)
                        user_files.append((timestamp, full_path))
                    except (IndexError, ValueError):
                        logger.warning(f"Unable to parse timestamp from filename: {filename}")
                        continue
            
            if user_files:
                # Sort by timestamp (descending) and select the most recent
                user_files.sort(key=lambda x: x[0], reverse=True)
                bundled_file_path = user_files[0][1]
                logger.info(f"Selected most recent bundled wallet file: {bundled_file_path}")
        
        if not bundled_file_path or not os.path.exists(bundled_file_path):
            logger.error(f"Bundled wallet file not found for user {user_id}")
            return []
        
        # Load the bundled wallet file
        with open(bundled_file_path, 'r') as f:
            bundled_data = json.load(f)
        
        # Extract wallet credentials and convert to API format
        wallets = []
        wallet_data = bundled_data.get("data", [])
        
        for wallet in wallet_data:
            wallet_name = wallet.get("name", "")
            stored_private_key = wallet.get("privateKey", "")
            
            if wallet_name and stored_private_key:
                try:
                    # Check if it's already base58 format or needs conversion
                    if is_base58_private_key(stored_private_key):
                        base58_private_key = stored_private_key
                        logger.info(f"Wallet {wallet_name}: Private key already in base58 format")
                    else:
                        # Convert from base64 to base58
                        base58_private_key = convert_base64_to_base58(stored_private_key)
                        logger.info(f"Wallet {wallet_name}: Converted private key from base64 to base58")
                    
                    # Final validation before adding to list
                    if not is_base58_private_key(base58_private_key):
                        logger.error(f"Wallet {wallet_name}: Final private key validation failed, skipping")
                        continue
                    
                    # Add to wallets list
                    wallets.append({
                        "name": wallet_name,
                        "privateKey": base58_private_key
                    })
                    
                    logger.info(f"Successfully loaded wallet credential for: {wallet_name}")
                    
                except Exception as e:
                    logger.error(f"Failed to process private key for wallet {wallet_name}: {str(e)}")
                    logger.error(f"Private key format details - length: {len(stored_private_key)}, starts_with: {stored_private_key[:8] if len(stored_private_key) >= 8 else 'too_short'}")
                    continue
        
        logger.info(f"Successfully loaded {len(wallets)} wallet credentials from bundled file")
        return wallets
        
    except Exception as e:
        logger.error(f"Failed to load wallet credentials from bundled file: {e}")
        return []


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
        
        # Get image data from session if uploaded
        image_file_path = session_manager.get_session_value(user.id, "token_image_local_path")
        has_custom_image = session_manager.get_session_value(user.id, "has_custom_image", False)
        
        if not all([pumpfun_client, token_params, buy_amounts]):
            raise Exception("Missing required session data for token creation")
        
        # Show progress message
        progress_message = "🚀 **Creating Token with Initial Buys...**\n\n"
        if has_custom_image:
            progress_message += "⚠️ **Note**: Image upload temporarily disabled due to API limitations\n"
            progress_message += "🖼️ Your image was saved but token will be created without it for now\n"
        progress_message += "⏳ Creating your token and executing initial purchases with configured amounts..."
        
        await query.edit_message_text(
            progress_message,
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
        
        # CRITICAL FIX: Use the same address source for balance check and token creation
        # Instead of loading from bundled file, use the bundled_wallet_storage to ensure consistency
        try:
            # Get airdrop wallet address to load user-specific bundled wallets
            airdrop_wallet_address = session_manager.get_session_value(user.id, "airdrop_wallet_address")
            if not airdrop_wallet_address:
                raise Exception("Airdrop wallet address not found in session")
            
            # Load bundled wallets using the same method as balance checks
            from bot.utils.wallet_storage import bundled_wallet_storage
            bundled_wallets_data = bundled_wallet_storage.load_bundled_wallets(airdrop_wallet_address, user.id)
            
            if not bundled_wallets_data:
                raise Exception(f"No bundled wallets found for user {user.id}")
            
            # Convert to the format expected by the API, but using the SAME addresses as balance check
            wallets = []
            for wallet in bundled_wallets_data:
                wallet_name = wallet.get("name", "")
                # Try multiple field names for wallet address - bundled storage may use different field names
                wallet_address = (
                    wallet.get("address") or 
                    wallet.get("publicKey") or 
                    wallet.get("public_key") or
                    wallet.get("walletAddress")
                )
                stored_private_key = wallet.get("privateKey", "") or wallet.get("private_key", "")
                
                # Debug logging to see what fields are available
                logger.info(f"Processing wallet {wallet_name}: available fields = {list(wallet.keys())}")
                logger.info(f"Wallet {wallet_name}: address='{wallet_address}', has_private_key={bool(stored_private_key)}")
                
                if not all([wallet_name, wallet_address, stored_private_key]):
                    logger.warning(f"Skipping incomplete wallet data: {wallet_name} - missing fields: name={bool(wallet_name)}, address={bool(wallet_address)}, privateKey={bool(stored_private_key)}")
                    continue
                
                try:
                    # Check if it's already base58 format or needs conversion
                    if is_base58_private_key(stored_private_key):
                        base58_private_key = stored_private_key
                        logger.info(f"Wallet {wallet_name}: Private key already in base58 format")
                    else:
                        # Convert from base64 to base58
                        base58_private_key = convert_base64_to_base58(stored_private_key)
                        logger.info(f"Wallet {wallet_name}: Converted private key from base64 to base58")
                    
                    # Final validation before adding to list
                    if not is_base58_private_key(base58_private_key):
                        logger.error(f"Wallet {wallet_name}: Final private key validation failed, skipping")
                        continue
                    
                    # Add to wallets list with consistent addressing
                    wallets.append({
                        "name": wallet_name,
                        "privateKey": base58_private_key,
                        "address": wallet_address  # Include address for verification
                    })
                    
                    logger.info(f"Successfully loaded wallet: {wallet_name} -> {wallet_address[:8]}...")
                    
                except Exception as e:
                    logger.error(f"Failed to process private key for wallet {wallet_name}: {str(e)}")
                    continue
            
        except Exception as storage_error:
            logger.warning(f"Failed to load from bundled_wallet_storage, falling back to bundled file: {storage_error}")
            # Fallback to original method if storage fails
            wallets = load_wallet_credentials_from_bundled_file(user.id)
        
        logger.info(f"Loaded wallet credentials for user {user.id}: {len(wallets)} wallets from bundled storage")
        
        # Log the addresses being used for token creation to verify they match balance checks
        for wallet in wallets:
            wallet_name = wallet.get("name", "Unknown")
            wallet_address = wallet.get("address", "No address")
            logger.info(f"Token creation will use: {wallet_name} -> {wallet_address}")
        
        if not wallets:
            raise Exception("No wallet credentials found in bundled wallet storage. Please ensure bundled wallets are properly created.")
        
        # CRITICAL FIX: Only include wallets that have corresponding buy amounts configured
        # This ensures we don't send unfunded wallets to the API
        required_wallet_names = ["DevWallet"]  # Always include DevWallet
        
        # Only add bundled wallets that will have buy amounts (based on buy_amounts config)
        if "First Bundled Wallets" in buy_amounts and buy_amounts["First Bundled Wallets"] > 0:
            # Only include one bundled wallet since we configure buy amounts per group, not per individual wallet
            required_wallet_names.append("First Bundled Wallet 1")
        
        filtered_wallets = []
        for wallet in wallets:
            if wallet["name"] in required_wallet_names:
                filtered_wallets.append(wallet)
        
        wallets = filtered_wallets
        
        # CRITICAL FIX: Create BuyAmounts object based on actual wallets being sent
        buy_amounts_kwargs = {
            "dev_wallet_buy_sol": dev_wallet_amount
        }
        
        # Only add buy amounts for wallets that are actually included in the request
        wallet_names = [wallet["name"] for wallet in wallets]
        if "First Bundled Wallet 1" in wallet_names:
            buy_amounts_kwargs["first_bundled_wallet_1_buy_sol"] = first_bundled_amount
        
        logger.info(f"BuyAmounts configuration: {buy_amounts_kwargs}")
        buy_amounts_obj = BuyAmounts(**buy_amounts_kwargs)
        
        # Ensure we have at least DevWallet and validate wallet funding
        wallet_names = [wallet["name"] for wallet in wallets]
        if "DevWallet" not in wallet_names:
            raise Exception("DevWallet not found in bundled wallet file")
        
        # Ensure we have at least one other wallet for token creation
        if len(wallets) < 2:
            raise Exception("At least one additional wallet (beyond DevWallet) is required for token creation")
        
        logger.info(f"Final wallets for token creation: {wallet_names}")
        logger.info(f"Buy amounts configuration: {buy_amounts_kwargs}")
        
        # Log warning about wallet funding (this is the real issue from logs)
        logger.warning("⚠️  IMPORTANT: Ensure all wallets have sufficient SOL balance before token creation")
        logger.warning(f"Each wallet needs approximately 0.008+ SOL for fees, rent, and buy amounts")
        
        logger.info(f"Final wallets selected for token creation: {wallet_names}")
        logger.info(f"Creating token with {len(wallets)} wallets and buy amounts: {buy_amounts_kwargs}")
        start_time = time.time()
        
        # Create token and execute buys with user-configured amounts and image
        token_result = pumpfun_client.create_token_and_buy(
            token_params=token_creation_params,
            buy_amounts=buy_amounts_obj,
            wallets=wallets,  # NEW: Required wallets parameter
            image_file_path=image_file_path if has_custom_image else None
        )
        
        # Debug: Log the exact API response structure
        logger.info(f"Token creation API response keys: {list(token_result.keys()) if isinstance(token_result, dict) else 'Not a dict'}")
        logger.info(f"Token creation API response structure: {token_result}")
        
        execution_time = time.time() - start_time
        
        # Cleanup temporary image file after successful creation
        if has_custom_image and image_file_path:
            try:
                from bot.utils.image_utils import TelegramImageProcessor
                image_processor = TelegramImageProcessor()
                cleaned_count = image_processor.cleanup_temp_files(user.id)
                logger.info(f"Cleaned up {cleaned_count} temp image files for user {user.id}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp image files: {cleanup_error}")
        
        # Store final results - normalize API response format
        logger.info("Attempting to extract mint address from API response")
        
        mint_address = None
        bundle_id = ""
        
        try:
            # Try multiple possible field names where mint address might be stored
            possible_mint_fields = [
                "mintAddress", "mint_address", "mint", "tokenAddress", "token_address", 
                "contractAddress", "contract_address", "address", "tokenMint", "token_mint"
            ]
            
            for field in possible_mint_fields:
                if field in token_result and token_result[field]:
                    mint_address = token_result[field]
                    logger.info(f"Found mint address in field '{field}': {mint_address}")
                    break
            
            # Try nested fields if mint address not found at top level
            if not mint_address:
                logger.info("Mint address not found at top level, checking nested fields")
                for key, value in token_result.items():
                    if isinstance(value, dict):
                        for nested_field in possible_mint_fields:
                            if nested_field in value and value[nested_field]:
                                mint_address = value[nested_field]
                                logger.info(f"Found mint address in nested field '{key}.{nested_field}': {mint_address}")
                                break
                        if mint_address:
                            break
            
            # Try to extract from message or any string field that might contain the mint address
            if not mint_address:
                logger.info("Mint address not found in structured fields, checking message content")
                mint_pattern = r'[A-Za-z0-9]{32,50}'  # Solana address pattern
                for key, value in token_result.items():
                    if isinstance(value, str) and len(value) > 30:
                        matches = re.findall(mint_pattern, value)
                        if matches:
                            # Look for addresses that might be mint addresses (not transaction signatures)
                            for match in matches:
                                if len(match) >= 32 and len(match) <= 44:  # Typical Solana address length
                                    mint_address = match
                                    logger.info(f"Extracted mint address from string field '{key}': {mint_address}")
                                    break
                            if mint_address:
                                break
            
            # Extract bundle ID
            bundle_id = token_result.get("bundleId") or token_result.get("bundle_id", "")
            
        except Exception as extraction_error:
            logger.error(f"Error during mint address extraction: {str(extraction_error)}")
            # Continue with empty mint_address to trigger the fallback below
        
        logger.info(f"Final extracted mint_address: {mint_address}")
        logger.info(f"Final extracted bundle_id: {bundle_id}")
        
        if not mint_address:
            logger.error(f"Mint address extraction failed. Available keys: {list(token_result.keys())}")
            logger.error(f"Full response for debugging: {token_result}")
            
            # Try one more time with a hardcoded extraction from known API log format
            try:
                # From API logs: "Token NAME created and initial buys completed successfully in bundle ID. Mint: ADDRESS"
                response_str = str(token_result)
                mint_match = re.search(r'Mint[:\s]+([A-Za-z0-9]{32,50})', response_str, re.IGNORECASE)
                if mint_match:
                    mint_address = mint_match.group(1)
                    logger.info(f"Extracted mint address using regex pattern: {mint_address}")
            except Exception as regex_error:
                logger.error(f"Regex extraction also failed: {str(regex_error)}")
                
            if not mint_address:
                raise Exception(f"Token creation succeeded but mint address not found in response. Available keys: {list(token_result.keys())}")
            
        logger.info(f"Successfully extracted mint address: {mint_address}")
            
        session_manager.update_session_value(user.id, "token_address", mint_address)
        session_manager.update_session_value(user.id, "token_creation_signature", bundle_id)
        session_manager.update_session_value(user.id, "final_creation_results", token_result)
        
        # Store the created token in persistent storage
        storage_status = "❌ Storage failed"
        if mint_address:
            # Get token parameters for storage
            token_params = session_manager.get_session_value(user.id, "token_params") or {}
            token_name = token_params.get("name", "Unknown Token")
            
            logger.info(f"Attempting to store token: mint_address={mint_address}, token_name={token_name}, user_id={user.id}")
            
            # Store the created token
            storage_success = token_storage.store_token(
                user_id=user.id,
                mint_address=mint_address,
                token_name=token_name,
                bundle_id=bundle_id
            )
            
            if storage_success:
                storage_status = "✅ Token saved to storage"
                logger.info(f"✅ Token {mint_address} ({token_name}) stored successfully for user {user.id}")
            else:
                storage_status = "❌ Token storage failed"
                logger.error(f"❌ Failed to store token {mint_address} ({token_name}) for user {user.id}")
        else:
            logger.error(f"❌ Cannot store token - mint_address is empty for user {user.id}")
        
        # Execute additional buys for remaining child wallets if configured
        additional_child_amount = buy_amounts.get("Additional Child Wallets")
        if additional_child_amount and additional_child_amount > 0:
            additional_count = wallet_group_counts.get("Additional Child Wallets", 0)
            if additional_count > 0:
                logger.info(f"Executing additional buys for {additional_count} remaining child wallets")
                try:
                    # Execute batch buy for remaining wallets
                    additional_result = pumpfun_client.batch_buy_token(
                        mint_address=mint_address,
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
                "token_address": mint_address,
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
            "token_address": mint_address,
            "total_operations": total_participating_wallets,
            "successful_operations": total_participating_wallets,  # Assume all successful for now
            "failed_operations": 0,
            "execution_time": execution_time,
            "buy_amounts": buy_amounts,
            "wallet_group_counts": wallet_group_counts,
            "storage_status": storage_status  # Add storage status to results
        }
        
        try:
            await query.edit_message_text(
                format_bundle_operation_results(results_with_token),
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as telegram_error:
            # If there's a Telegram parsing error, try sending without markdown
            logger.warning(f"Telegram markdown parsing failed, retrying without markdown: {str(telegram_error)}")
            try:
                # Create a simple text version without markdown
                simple_message = (
                    f"✅ Token Creation Successful!\n\n"
                    f"Token Address: {mint_address}\n"
                    f"Execution Time: {execution_time:.2f}s\n"
                    f"Total Operations: {total_participating_wallets}\n"
                    f"Storage: {storage_status}\n\n"
                    f"Your token is now live on the blockchain!"
                )
                await query.edit_message_text(
                    simple_message,
                    reply_markup=keyboard
                )
            except Exception as fallback_error:
                logger.error(f"Both markdown and fallback message failed: {str(fallback_error)}")
                raise telegram_error
        
        return ConversationState.BUNDLE_OPERATION_COMPLETE
        
    except Exception as e:
        logger.error(
            f"Final token creation failed for user {user.id}: {str(e)}",
            extra={"user_id": user.id}
        )
        
        # Cleanup temp image files on error too
        try:
            has_custom_image = session_manager.get_session_value(user.id, "has_custom_image", False)
            if has_custom_image:
                from bot.utils.image_utils import TelegramImageProcessor
                image_processor = TelegramImageProcessor()
                cleaned_count = image_processor.cleanup_temp_files(user.id)
                logger.info(f"Cleaned up {cleaned_count} temp image files after error for user {user.id}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to cleanup temp image files after error: {cleanup_error}")
        
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
