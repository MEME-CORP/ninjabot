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
        
        # NEW LOGIC: Implement proper wallet batching according to API requirements
        # API can only handle 4 wallets max for token creation, remaining wallets use batch-buy
        
        if not wallets:
            raise Exception("No wallet credentials found in bundled wallet storage. Please ensure bundled wallets are properly created.")
        
        logger.info(f"Total wallets loaded: {len(wallets)}")
        
        # Separate wallets into creation batch (max 4) and additional batch (remaining)
        # Always prioritize DevWallet for token creation
        dev_wallet = None
        other_wallets = []
        
        for wallet in wallets:
            if wallet["name"] == "DevWallet":
                dev_wallet = wallet
            else:
                other_wallets.append(wallet)
        
        if not dev_wallet:
            raise Exception("DevWallet not found in bundled wallet file")
        
        # Select wallets for token creation (max 4 total, including DevWallet)
        creation_wallets = [dev_wallet]
        
        # Add up to 3 additional wallets for token creation
        max_additional_for_creation = min(3, len(other_wallets))
        for i in range(max_additional_for_creation):
            creation_wallets.append(other_wallets[i])
        
        # Remaining wallets will use batch buy after token creation
        batch_buy_wallets = other_wallets[max_additional_for_creation:]
        
        logger.info(f"Token creation wallets ({len(creation_wallets)}): {[w['name'] for w in creation_wallets]}")
        logger.info(f"Batch buy wallets ({len(batch_buy_wallets)}): {[w['name'] for w in batch_buy_wallets]}")
        
        # Create BuyAmounts object for token creation wallets only
        buy_amounts_kwargs = {
            "dev_wallet_buy_sol": dev_wallet_amount
        }
        
        # Add buy amounts for creation wallets (excluding DevWallet)
        creation_wallet_names = [wallet["name"] for wallet in creation_wallets]
        
        # Map wallet names to buy amount fields in BuyAmounts class
        wallet_to_field_map = {
            "First Bundled Wallet 1": "first_bundled_wallet_1_buy_sol",
            "First Bundled Wallet 2": "first_bundled_wallet_2_buy_sol", 
            "First Bundled Wallet 3": "first_bundled_wallet_3_buy_sol",
            "First Bundled Wallet 4": "first_bundled_wallet_4_buy_sol"
        }
        
        for wallet_name in creation_wallet_names:
            if wallet_name != "DevWallet" and wallet_name in wallet_to_field_map:
                # Use the configured buy amount for bundled wallets
                buy_amounts_kwargs[wallet_to_field_map[wallet_name]] = first_bundled_amount
        
        logger.info(f"Final BuyAmounts configuration for token creation: {buy_amounts_kwargs}")
        buy_amounts_obj = BuyAmounts(**buy_amounts_kwargs)
        
        # Validate we have the required setup for token creation
        if len(creation_wallets) < 1:
            raise Exception("At least DevWallet is required for token creation")
        
        creation_wallet_names = [wallet["name"] for wallet in creation_wallets]
        logger.info(f"Creating token with {len(creation_wallets)} wallets: {creation_wallet_names}")
        
        # Log warning about wallet funding
        logger.warning("⚠️  IMPORTANT: Ensure all wallets have sufficient SOL balance before token creation")
        logger.warning(f"Each wallet needs approximately 0.008+ SOL for fees, rent, and buy amounts")
        
        logger.info(f"Starting token creation with {len(creation_wallets)} wallets")
        start_time = time.time()
        
        # Create token and execute buys with selected creation wallets
        token_result = pumpfun_client.create_token_and_buy(
            token_params=token_creation_params,
            buy_amounts=buy_amounts_obj,
            wallets=creation_wallets,  # Use only creation wallets (max 4)
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
        
        # Execute batch buy for remaining wallets if any
        if batch_buy_wallets and len(batch_buy_wallets) > 0:
            logger.info(f"Executing batch buy for {len(batch_buy_wallets)} remaining wallets")
            try:
                # Use the same buy amount as configured for bundled wallets
                batch_buy_amount = first_bundled_amount
                
                batch_result = pumpfun_client.batch_buy_token(
                    mint_address=mint_address,
                    sol_amount_per_wallet=batch_buy_amount,
                    wallets=batch_buy_wallets,
                    slippage_bps=2500
                )
                logger.info(f"Batch buy completed successfully: {batch_result}")
                
                # Store batch buy results in session
                session_manager.update_session_value(user.id, "batch_buy_results", batch_result)
                
            except Exception as batch_error:
                logger.warning(f"Batch buy failed (token creation was successful): {str(batch_error)}")
                # Don't fail the entire operation if batch buy fails
                session_manager.update_session_value(user.id, "batch_buy_error", str(batch_error))
        
        logger.info(
            f"Final token creation completed for user {user.id}",
            extra={
                "user_id": user.id,
                "token_address": mint_address,
                "execution_time": execution_time
            }
        )
        
        # REDIRECT TO BUNDLER MANAGEMENT: Set up session data for the newly created token
        airdrop_wallet_address = session_manager.get_session_value(user.id, "airdrop_wallet_address")
        
        # Prepare token data for bundler management
        token_data = {
            "mint_address": mint_address,
            "token_name": token_params["name"],
            "token_symbol": token_params["ticker"],
            "created_at": time.time(),
            "bundle_id": bundle_id,
            "airdrop_wallet_address": airdrop_wallet_address
        }
        
        # Set the selected token for bundler management
        session_manager.update_session_value(user.id, "selected_token", token_data)
        logger.info(f"Set selected token for bundler management: {token_data['token_name']} ({mint_address}) for user {user.id}")
        
        # Create success message with redirect to bundler management
        keyboard = InlineKeyboardMarkup([
            [build_button("🟢 Buy with Dev Wallet", f"token_operation_buy_dev")],
            [build_button("🟢 Buy with Bundled Wallets", f"token_operation_buy_bundled")],
            [build_button("🟢 Buy with All Wallets", f"token_operation_buy_all")],
            [build_button("🔴 Sell with Dev Wallet", f"token_operation_sell_dev")],
            [build_button("🔴 Sell with Bundled Wallets", f"token_operation_sell_bundled")],
            [build_button("🔴 Sell with All Wallets", f"token_operation_sell_all")],
            [build_button("🔄 Create Another Token", "start_token_creation")],
            [build_button("« Back to Activities", "back_to_activities")]
        ])
        
        # Calculate total participating wallets and create success message
        total_creation_wallets = len(creation_wallets)
        total_batch_wallets = len(batch_buy_wallets)
        total_participating_wallets = total_creation_wallets + total_batch_wallets
        
        # Build status message based on batch buy results
        batch_status = ""
        if batch_buy_wallets:
            batch_buy_error = session_manager.get_session_value(user.id, "batch_buy_error")
            if batch_buy_error:
                batch_status = f"\n⚠️ **Batch Buy Status:** Failed ({len(batch_buy_wallets)} wallets) - {batch_buy_error}"
            else:
                batch_status = f"\n✅ **Batch Buy Status:** Success ({len(batch_buy_wallets)} wallets)"
        
        success_message = (
            f"🎉 **Token Created Successfully!**\n\n"
            f"**Token:** {token_params['name']} ({token_params['ticker']})\n"
            f"**Mint Address:** `{mint_address}`\n"
            f"**Bundle ID:** `{bundle_id}`\n"
            f"**Execution Time:** {execution_time:.2f}s\n"
            f"**Token Creation:** {total_creation_wallets} wallets\n"
            f"**Total Operations:** {total_participating_wallets} wallets{batch_status}\n\n"
            f"✅ **Ready for Trading Operations**\n\n"
            f"Your token is now live! You can perform additional buy/sell operations using the buttons below:"
        )
        
        try:
            await query.edit_message_text(
                success_message,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as telegram_error:
            # If there's a Telegram parsing error, try sending without markdown
            logger.warning(f"Telegram markdown parsing failed, retrying without markdown: {str(telegram_error)}")
            try:
                # Create a simple text version without markdown
                simple_message = (
                    f"Token Created Successfully!\n\n"
                    f"Token: {token_params['name']} ({token_params['ticker']})\n"
                    f"Mint Address: {mint_address}\n"
                    f"Bundle ID: {bundle_id}\n"
                    f"Execution Time: {execution_time:.2f}s\n\n"
                    f"Your token is now live! Use the buttons below for trading operations."
                )
                await query.edit_message_text(
                    simple_message,
                    reply_markup=keyboard
                )
            except Exception as fallback_error:
                logger.error(f"Both markdown and fallback message failed: {str(fallback_error)}")
                raise telegram_error
        
        # CRITICAL: Return TOKEN_MANAGEMENT_OPTIONS state to enable trading operations
        return ConversationState.TOKEN_MANAGEMENT_OPTIONS
        
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
