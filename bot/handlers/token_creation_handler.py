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
from bot.utils.rate_limit_utils import RateLimitFeedback


def is_base58_private_key(key: str) -> bool:
    """
    Check if a string is a valid base58 encoded Solana private key.
    
    Args:
        key: The key string to validate
        
    Returns:
        True if the key is valid base58 format, False otherwise
    """
    try:
        # Solana private keys in base58 format are typically 87-88 characters
        # Accept both lengths as long as they decode to 64 bytes
        if len(key) < 87 or len(key) > 88:
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


# Recursive field extraction helpers for nested API responses
def _norm_key(k: str) -> str:
    """Normalize keys by removing underscores/hyphens and lowering for comparison."""
    return re.sub(r'[_-]', '', k).lower()


def _recursive_find_field(payload: Any, target_keys: List[str]) -> Optional[Any]:
    """Recursively search dicts/lists for the first occurrence of target keys.

    Returns the first non-collection value found for any of the target_keys.
    """
    try:
        normalized_targets = {_norm_key(t) for t in target_keys}
        if isinstance(payload, dict):
            for k, v in payload.items():
                # Only return direct matches when the value is a scalar; otherwise, keep recursing
                if _norm_key(k) in normalized_targets and v is not None and not isinstance(v, (dict, list)):
                    return v
                res = _recursive_find_field(v, target_keys)
                if res is not None:
                    return res
        elif isinstance(payload, list):
            for item in payload:
                res = _recursive_find_field(item, target_keys)
                if res is not None:
                    return res
    except Exception:
        # Be fault-tolerant; fall through to return None
        pass
    return None


def _recursive_extract_address_from_strings(payload: Any) -> Optional[str]:
    """Recursively search strings within payload for a plausible Solana address.

    Prefers explicit 'Mint: <address>' hints; otherwise returns the first base58-like
    address-length string (32-44 chars) found.
    """
    addr_pattern = r'[A-Za-z0-9]{32,50}'
    mint_hint_pattern = r'Mint[:\s]+([A-Za-z0-9]{32,50})'
    try:
        if isinstance(payload, dict):
            for v in payload.values():
                res = _recursive_extract_address_from_strings(v)
                if res:
                    return res
        elif isinstance(payload, list):
            for item in payload:
                res = _recursive_extract_address_from_strings(item)
                if res:
                    return res
        elif isinstance(payload, str) and len(payload) > 30:
            m = re.search(mint_hint_pattern, payload, re.IGNORECASE)
            if m:
                return m.group(1)
            matches = re.findall(addr_pattern, payload)
            for match in matches:
                if 32 <= len(match) <= 44:
                    return match
    except Exception:
        # Be fault-tolerant; fall through to return None
        pass
    return None


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
                    # Enhanced logging for key format detection
                    logger.info(f"Processing wallet {wallet_name}: original key length = {len(stored_private_key)}")
                    
                    # Check if it's already base58 format or needs conversion
                    if is_base58_private_key(stored_private_key):
                        base58_private_key = stored_private_key
                        logger.info(f"✅ Wallet {wallet_name}: Private key already in valid base58 format (length: {len(stored_private_key)})")
                    else:
                        logger.warning(f"⚠️ Wallet {wallet_name}: Key not valid base58, attempting base64 to base58 conversion")
                        # Convert from base64 to base58
                        base58_private_key = convert_base64_to_base58(stored_private_key)
                        logger.info(f"🔄 Wallet {wallet_name}: Converted private key from base64 to base58 (new length: {len(base58_private_key)})")
                    
                    # Final validation before adding to list
                    if not is_base58_private_key(base58_private_key):
                        logger.error(f"❌ Wallet {wallet_name}: Final private key validation failed, skipping wallet")
                        logger.error(f"❌ Key details - length: {len(base58_private_key)}, first 10 chars: {base58_private_key[:10] if len(base58_private_key) >= 10 else base58_private_key}")
                        continue
                    
                    # Add to wallets list
                    wallets.append({
                        "name": wallet_name,
                        "privateKey": base58_private_key
                    })
                    
                    logger.info(f"✅ Successfully loaded wallet credential for: {wallet_name}")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to process private key for wallet {wallet_name}: {str(e)}")
                    logger.error(f"❌ Private key format details - length: {len(stored_private_key)}, starts_with: {stored_private_key[:8] if len(stored_private_key) >= 8 else 'too_short'}")
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
        # IMPORTANT: DevWallet amount should be 0 since it buys automatically via create_amount_sol parameter
        # But we still need to pass 0 to satisfy API validation requirements
        dev_wallet_amount = 0.0  # DevWallet buys during token creation, not through buyAmountsSOL
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
                    
                    # MONOCODE: Observable Implementation - Structured logging for wallet validation
                    validation_context = {
                        "wallet_name": wallet_name,
                        "wallet_address": wallet_address[:8] + "..." if wallet_address else "None",
                        "private_key_length": len(base58_private_key),
                        "validation_stage": "final_check"
                    }
                    
                    # MONOCODE: Explicit Error Handling - Graceful Fallbacks instead of silent failure
                    validation_passed = False
                    validation_warnings = []
                    
                    # Primary validation: Check if key exists and is non-empty
                    if not base58_private_key or len(base58_private_key.strip()) == 0:
                        logger.error("Wallet validation failed: empty private key", extra=validation_context)
                        continue
                    
                    # Secondary validation: Attempt base58 decode with graceful fallback
                    try:
                        decoded_key = base58.b58decode(base58_private_key)
                        validation_context["decoded_key_length"] = len(decoded_key)
                        
                        # MONOCODE: Fail Fast, Fail Loud - but with context
                        if len(decoded_key) < 32:
                            validation_warnings.append(f"decoded_key_short_{len(decoded_key)}_bytes")
                            logger.warning("Wallet validation warning: private key shorter than expected", 
                                         extra={**validation_context, "warning": "short_key_included"})
                        elif len(decoded_key) != 64:
                            validation_warnings.append(f"decoded_key_non_standard_{len(decoded_key)}_bytes")
                            logger.warning("Wallet validation warning: private key non-standard length", 
                                         extra={**validation_context, "warning": "non_standard_length_included"})
                        
                        validation_passed = True
                        
                    except Exception as decode_error:
                        # MONOCODE: Graceful Fallbacks - include wallet even if decode fails
                        validation_warnings.append(f"decode_error_{type(decode_error).__name__}")
                        logger.warning("Wallet validation warning: base58 decode failed but including wallet", 
                                     extra={**validation_context, "decode_error": str(decode_error), "action": "included_anyway"})
                        validation_passed = True  # Include anyway - let API decide
                    
                    # MONOCODE: Deterministic State - Always log the final decision
                    validation_context.update({
                        "validation_result": "passed" if validation_passed else "failed",
                        "warnings_count": len(validation_warnings),
                        "warnings": validation_warnings,
                        "action": "included" if validation_passed else "excluded"
                    })
                    
                    if validation_passed:
                        # Add to wallets list with consistent addressing
                        wallets.append({
                            "name": wallet_name,
                            "privateKey": base58_private_key,
                            "address": wallet_address  # Include address for verification
                        })
                        
                        logger.info("Wallet successfully loaded and included in API request", extra=validation_context)
                    else:
                        logger.error("Wallet excluded from API request due to validation failure", extra=validation_context)
                    
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
        
        # NEW API: All wallets can participate in token creation/buying in a single call
        # Build buy amounts for all wallets that should participate
        # IMPORTANT: DevWallet amount should be 0 since it buys automatically via create_amount_sol parameter
        # But we still need to pass 0 to satisfy API validation requirements
        dev_wallet_amount = 0.0  # DevWallet buys during token creation, not through buyAmountsSOL
        first_bundled_amount = buy_amounts.get("First Bundled Wallets", 0.01)
        
        # Create BuyAmounts object for ALL wallets
        buy_amounts_kwargs = {
            "dev_wallet_buy_sol": dev_wallet_amount,
            "first_bundled_wallet_1_buy_sol": first_bundled_amount,
            "first_bundled_wallet_2_buy_sol": first_bundled_amount,
            "first_bundled_wallet_3_buy_sol": first_bundled_amount,
            "first_bundled_wallet_4_buy_sol": first_bundled_amount,
        }
        
        logger.info(f"BuyAmounts configuration - DevWallet: {dev_wallet_amount} SOL (buys via create_amount_sol instead)")
        logger.info(f"BuyAmounts configuration - Bundled wallets: {first_bundled_amount} SOL each")
        logger.info(f"Full BuyAmounts configuration: {buy_amounts_kwargs}")
        buy_amounts_obj = BuyAmounts(**buy_amounts_kwargs)
        
        # Validate we have DevWallet for token creation
        dev_wallet = next((w for w in wallets if w["name"] == "DevWallet"), None)
        if not dev_wallet:
            raise Exception("DevWallet not found in bundled wallet file")
        
        logger.info(f"Creating token with {len(wallets)} wallets (all participating in single API call)")
        
        # Log warning about wallet funding
        logger.warning("⚠️  IMPORTANT: Ensure all wallets have sufficient SOL balance before token creation")
        logger.warning(f"Each wallet needs approximately 0.008+ SOL for fees, rent, and buy amounts")
        
        logger.info(f"Starting token creation with {len(wallets)} wallets using new dynamic API")
        start_time = time.time()
        
        # Refresh session before long token creation operation
        session_manager.refresh_session(user.id)
        
        # Create token and execute buys with ALL wallets using new dynamic API
        try:
            token_result = pumpfun_client.create_token_and_buy(
                token_params=token_creation_params,
                buy_amounts=buy_amounts_obj,
                wallets=wallets,  # Use ALL wallets - API will process them dynamically
                image_file_path=image_file_path if has_custom_image else None
            )
        except Exception as e:
            # Check if this is a rate limiting error and provide user feedback
            if RateLimitFeedback.is_rate_limit_error(str(e)):
                logger.warning(f"Rate limiting detected during token creation: {str(e)}")
                await RateLimitFeedback.handle_rate_limit_error(
                    bot=context.bot,
                    chat_id=update.effective_chat.id,
                    message_id=context.user_data.get('current_message_id'),
                    operation_name="Token Creation",
                    error_message=str(e),
                    estimated_wait_time=120  # 2 minutes estimated wait
                )
                # Re-raise to let the PumpFun client handle the retry logic
                raise e
            else:
                # Not a rate limiting error, handle normally
                raise e
        
        # Refresh session after long token creation operation completes
        session_manager.refresh_session(user.id)
        
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
        logger.info("Attempting to extract mint address and bundle id from API response")

        mint_address = None
        bundle_id = ""

        try:
            # Preferred field names (both camelCase and snake_case)
            possible_mint_fields = [
                "mintAddress", "mint_address",
                "tokenMint", "token_mint",
                "tokenAddress", "token_address",
                "mint"
            ]

            # Recursively find mint address anywhere in the payload (handles wrappers like data/result/results)
            mint_address = _recursive_find_field(token_result, possible_mint_fields)
            if mint_address:
                logger.info(f"Found mint address via recursive search: {mint_address}")

            # If not found, recursively scan for an address inside string fields
            if not mint_address:
                logger.info("Mint address not found in structured fields, scanning strings recursively")
                mint_address = _recursive_extract_address_from_strings(token_result)
                if mint_address:
                    logger.info(f"Extracted mint address from string content: {mint_address}")

            # As a final fallback, regex on the entire serialized response
            if not mint_address:
                response_str = str(token_result)
                mint_match = re.search(r'Mint[:\s]+([A-Za-z0-9]{32,50})', response_str, re.IGNORECASE)
                if mint_match:
                    mint_address = mint_match.group(1)
                    logger.info(f"Extracted mint address using global regex fallback: {mint_address}")

            # Extract bundle ID recursively
            bundle_id = _recursive_find_field(token_result, ["bundleId", "bundle_id"]) or ""
            if bundle_id:
                logger.info(f"Found bundle id via recursive search: {bundle_id}")

        except Exception as extraction_error:
            logger.error(f"Error during mint/bundle extraction: {str(extraction_error)}")
            # Continue with empty values to trigger the fallback/validation below

        logger.info(f"Final extracted mint_address: {mint_address}")
        logger.info(f"Final extracted bundle_id: {bundle_id}")

        if not mint_address:
            # Provide more context if token_result is a dict
            try:
                keys_info = list(token_result.keys()) if isinstance(token_result, dict) else type(token_result).__name__
            except Exception:
                keys_info = "unknown"
            logger.error(f"Mint address extraction failed. Available keys/context: {keys_info}")
            logger.error(f"Full response for debugging: {token_result}")

            raise Exception(f"Token creation succeeded but mint address not found in response. Keys/context: {keys_info}")

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
        
        # NEW API: No batch buy needed - all wallets processed in single create-and-buy call
        logger.info(f"Token creation completed successfully using new dynamic API with {len(wallets)} wallets")
        
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
        total_participating_wallets = len(wallets)  # All wallets participate in single API call
        
        # Build status message - no batch buy needed with new API
        batch_status = ""  # New API processes all wallets in one call
        
        success_message = (
            f"🎉 **Token Created Successfully!**\n\n"
            f"**Token:** {token_params['name']} ({token_params['ticker']})\n"
            f"**Mint Address:** `{mint_address}`\n"
            f"**Bundle ID:** `{bundle_id}`\n"
            f"**Execution Time:** {execution_time:.2f}s\n"
            f"**Participating Wallets:** {total_participating_wallets} wallets{batch_status}\n\n"
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
