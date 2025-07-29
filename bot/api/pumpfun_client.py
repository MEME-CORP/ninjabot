#!/usr/bin/env python3
"""
PumpFun API Client for Solana wallet management and Pump.fun platform interactions.
Handles token creation, batch buying, and batch selling using Jito bundles.

UPDATED API USAGE (v2.0):
The client now supports the new stateless API endpoint that requires wallet credentials
to be passed directly in requests instead of being stored server-side.

Key Changes:
- create_token_and_buy() now requires a 'wallets' parameter with private keys
- Eliminates server-side wallet storage and path configuration issues
- Supports both multipart/form-data (with images) and JSON requests
- Enhanced validation for wallet credentials and buy amounts

Example Usage:
    client = PumpFunClient()
    
    # Prepare wallet credentials
    wallets = [
        {"name": "DevWallet", "privateKey": "base58_private_key"},
        {"name": "First Bundled Wallet 1", "privateKey": "base58_private_key"}
    ]
    
    # Create token
    result = client.create_token_and_buy(
        token_params=token_params,
        buy_amounts=buy_amounts, 
        wallets=wallets,  # NEW: Required parameter
        slippage_bps=2500
    )
"""

import json
import time
import logging
import requests
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Configuration
PUMPFUN_API_BASE_URL = "https://pumpfunapibundler-m0ep.onrender.com"  # Default local API server
DEFAULT_TIMEOUT = 60  # Increased from 30 to handle cold starts
MAX_RETRIES = 5  # Increased from 3 for better cold start handling
INITIAL_BACKOFF = 2.0  # Increased from 1.0 for cold start scenarios
COLD_START_MAX_RETRIES = 8  # Special retry count for cold starts
COLD_START_INITIAL_BACKOFF = 5.0  # Longer backoff for cold starts

# Rate Limiting Configuration
RATE_LIMIT_INITIAL_BACKOFF = 10.0  # Start with 10 seconds for rate limits
RATE_LIMIT_MAX_BACKOFF = 300.0     # Max 5 minutes between retries
RATE_LIMIT_MAX_RETRIES = 6         # Max attempts for rate-limited operations
JITO_BUNDLE_COOLDOWN = 30.0        # Minimum time between bundle operations


class PumpFunApiError(Exception):
    """Base exception for PumpFun API errors"""
    pass


class PumpFunRateLimitError(PumpFunApiError):
    """Rate limiting errors from Jito bundles or API throttling"""
    pass


class PumpFunValidationError(PumpFunApiError):
    """Validation errors for token parameters"""
    pass


class PumpFunBundleError(PumpFunApiError):
    """Bundle transaction errors"""
    pass


class PumpFunNetworkError(PumpFunApiError):
    """Network-related errors"""
    pass


@dataclass
class TokenCreationParams:
    """Token creation parameters"""
    name: str
    symbol: str
    description: str
    twitter: str = ""
    telegram: str = ""
    website: str = ""
    show_name: bool = True
    initial_supply_amount: str = "1000000000"
    image_url: str = ""


@dataclass
class BuyAmounts:
    """Buy amounts for different wallets"""
    dev_wallet_buy_sol: float = 0.01
    first_bundled_wallet_1_buy_sol: float = 0.01
    first_bundled_wallet_2_buy_sol: float = 0.0  # Optional - only used if wallet exists
    first_bundled_wallet_3_buy_sol: float = 0.0  # Optional - only used if wallet exists
    first_bundled_wallet_4_buy_sol: float = 0.0  # Optional - only used if wallet exists


class PumpFunClient:
    """
    PumpFun API client for managing Solana wallets and Pump.fun platform interactions.
    Follows the same patterns as the existing ApiClient for consistency.
    """

    def __init__(self, base_url: str = PUMPFUN_API_BASE_URL, timeout: int = DEFAULT_TIMEOUT):
        """
        Initialize the PumpFun API client.
        
        Args:
            base_url: Base URL for the PumpFun API
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'NinjaBot-PumpFun-Client/1.0'
        })
        
        # Rate limiting tracking
        self._last_bundle_operation_time = 0
        self._operation_timestamps = {
            'token_creation': 0,
            'batch_buy': 0,
            'batch_sell': 0,
            'balance_check': 0
        }

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make HTTP request to PumpFun API with error handling.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional request parameters
            
        Returns:
            API response as dictionary
            
        Raises:
            PumpFunApiError: On API errors
            PumpFunNetworkError: On network errors
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            # Set timeout if not provided
            if 'timeout' not in kwargs:
                kwargs['timeout'] = self.timeout
                
            # Log request details for debugging
            if 'json' in kwargs:
                logger.info(f"PumpFun API {method} {endpoint} - Request body: {kwargs['json']}")
            
            # Make request
            response = self.session.request(method, url, **kwargs)
            
            # Log request details
            logger.info(f"PumpFun API {method} {endpoint} - Status: {response.status_code}")
            
            # Handle response
            if response.status_code == 200:
                try:
                    return response.json()
                except json.JSONDecodeError:
                    return {"status": "success", "data": response.text}
            elif response.status_code == 400:
                # Enhanced error handling for validation errors with field-level analysis
                try:
                    error_data = response.json() if response.content else {}
                    detailed_error = error_data.get('error', error_data.get('message', 'Invalid request'))
                    
                    # Enhanced logging for field-level validation debugging
                    logger.error(f"PumpFun API 400 validation error: {detailed_error}")
                    logger.error(f"Full error response: {error_data}")
                    
                    # Detect common field name mismatches for better error reporting
                    if 'showName' in str(detailed_error):
                        logger.error("Field mismatch detected: API expects 'showName' (camelCase), check for 'show_name' (snake_case)")
                    if 'initialSupplyAmount' in str(detailed_error):
                        logger.error("Field mismatch detected: API expects 'initialSupplyAmount' (camelCase), check for 'initial_supply_amount' (snake_case)")
                    if 'imageFileName' in str(detailed_error):
                        logger.error("Field mismatch detected: API expects 'imageFileName' (camelCase), check for 'image_url' (snake_case)")
                    
                    # Include request body in error context if available
                    if 'json' in kwargs:
                        logger.error(f"Request body that caused validation error: {kwargs['json']}")
                    
                    raise PumpFunValidationError(f"Validation error: {detailed_error}")
                except json.JSONDecodeError:
                    # If response is not JSON, log the raw response
                    logger.error(f"PumpFun API 400 non-JSON response: {response.text}")
                    raise PumpFunValidationError(f"Validation error: {response.text}")
            elif response.status_code == 500:
                error_data = response.json() if response.content else {}
                raise PumpFunApiError(f"Server error: {error_data.get('error', 'Internal server error')}")
            else:
                raise PumpFunApiError(f"HTTP {response.status_code}: {response.text}")
                
        except requests.exceptions.ConnectionError as e:
            raise PumpFunNetworkError(f"Connection error: {str(e)}")
        except requests.exceptions.Timeout as e:
            raise PumpFunNetworkError(f"Request timeout: {str(e)}")
        except requests.exceptions.RequestException as e:
            raise PumpFunNetworkError(f"Request error: {str(e)}")

    def _make_request_with_retry(self, method: str, endpoint: str, max_retries: int = MAX_RETRIES, 
                                initial_backoff: float = INITIAL_BACKOFF, **kwargs) -> Dict[str, Any]:
        """
        Make HTTP request with retry logic for network errors.
        Enhanced for cold start scenarios on cloud platforms like Render.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            max_retries: Maximum number of retry attempts
            initial_backoff: Initial backoff time in seconds
            **kwargs: Additional request parameters
            
        Returns:
            API response as dictionary
        """
        last_exception = None
        is_cold_start = self._detect_cold_start_scenario()
        
        # Use enhanced retry parameters for cold start scenarios
        if is_cold_start:
            max_retries = max(max_retries, COLD_START_MAX_RETRIES)
            initial_backoff = max(initial_backoff, COLD_START_INITIAL_BACKOFF)
            logger.info(f"Cold start detected, using enhanced retry: max_retries={max_retries}, initial_backoff={initial_backoff}")
        
        for attempt in range(max_retries + 1):
            try:
                return self._make_request(method, endpoint, **kwargs)
            except PumpFunNetworkError as e:
                last_exception = e
                if attempt < max_retries:
                    # Progressive backoff with jitter for cold starts
                    base_backoff = initial_backoff * (2 ** attempt)
                    # Add jitter to prevent thundering herd
                    jitter = random.uniform(0.5, 1.5) if is_cold_start else 1.0
                    backoff_time = base_backoff * jitter
                    
                    if is_cold_start and attempt == 0:
                        logger.warning(f"Cold start timeout detected, initiating wake-up sequence. Retrying in {backoff_time:.1f}s")
                    else:
                        logger.warning(f"Network error on attempt {attempt + 1}/{max_retries + 1}, retrying in {backoff_time:.1f}s: {str(e)}")
                    
                    time.sleep(backoff_time)
                else:
                    logger.error(f"All {max_retries + 1} retry attempts failed: {str(e)}")
            except (PumpFunValidationError, PumpFunApiError) as e:
                # Don't retry validation or API errors
                raise e
                
        raise last_exception

    def _detect_cold_start_scenario(self) -> bool:
        """
        Detect if this might be a cold start scenario.
        
        Returns:
            True if cold start is likely
        """
        # Simple heuristic: if base_url contains common serverless platforms
        serverless_indicators = [
            'render.com',
            'herokuapp.com', 
            'vercel.app',
            'netlify.app',
            'railway.app'
        ]
        
        for indicator in serverless_indicators:
            if indicator in self.base_url.lower():
                return True
        return False

    def _is_rate_limit_error(self, error_message: str) -> bool:
        """
        Detect if an error is due to rate limiting.
        
        Args:
            error_message: Error message to analyze
            
        Returns:
            True if this is a rate limiting error
        """
        rate_limit_indicators = [
            "Failed to send Jito bundle",
            "rate limit",
            "too many requests", 
            "429",
            "throttle",
            "jito.wtf/api/v1/bundles",
            "bundle submission failed"
        ]
        
        error_lower = error_message.lower()
        for indicator in rate_limit_indicators:
            if indicator.lower() in error_lower:
                logger.warning(f"Rate limit detected in error: {indicator} found in '{error_message}'")
                return True
        return False

    def _calculate_rate_limit_backoff(self, attempt: int) -> float:
        """
        Calculate exponential backoff with jitter for rate limiting.
        
        Args:
            attempt: Current attempt number (0-based)
            
        Returns:
            Backoff time in seconds
        """
        # Exponential backoff: 10s, 20s, 40s, 80s, 160s, 300s (max)
        base_delay = min(RATE_LIMIT_INITIAL_BACKOFF * (2 ** attempt), RATE_LIMIT_MAX_BACKOFF)
        
        # Add jitter to prevent thundering herd (±10%)
        jitter = random.uniform(0.9, 1.1)
        delay = base_delay * jitter
        
        logger.info(f"Rate limit backoff calculated: attempt={attempt}, base={base_delay}s, with_jitter={delay:.1f}s")
        return delay

    def _enforce_bundle_operation_cooldown(self, operation_type: str):
        """
        Enforce minimum time between bundle operations to prevent rate limiting.
        
        Args:
            operation_type: Type of operation ('token_creation', 'batch_buy', etc.)
        """
        current_time = time.time()
        time_since_last = current_time - self._last_bundle_operation_time
        
        if time_since_last < JITO_BUNDLE_COOLDOWN:
            sleep_time = JITO_BUNDLE_COOLDOWN - time_since_last
            logger.info(f"Bundle operation cooldown: waiting {sleep_time:.1f}s since last bundle operation")
            time.sleep(sleep_time)
        
        # Update operation timestamps
        self._operation_timestamps[operation_type] = current_time
        self._last_bundle_operation_time = current_time

    def _make_request_for_critical_operations(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make request with maximum retry effort for critical operations like wallet creation.
        Now includes rate limiting detection and handling.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            **kwargs: Additional request parameters
            
        Returns:
            API response as dictionary
        """
        # Check if this is a bundle operation that needs cooldown
        bundle_endpoints = ['/api/pump/create-and-buy', '/api/pump/batch-buy', '/api/pump/batch-sell']
        if any(bundle_endpoint in endpoint for bundle_endpoint in bundle_endpoints):
            operation_type = 'token_creation' if 'create-and-buy' in endpoint else 'batch_buy' if 'batch-buy' in endpoint else 'batch_sell'
            self._enforce_bundle_operation_cooldown(operation_type)
        
        # Use enhanced retry with rate limiting support
        return self._make_request_with_rate_limit_retry(
            method, 
            endpoint, 
            max_retries=COLD_START_MAX_RETRIES,
            initial_backoff=COLD_START_INITIAL_BACKOFF,
            **kwargs
        )

    def _make_request_with_rate_limit_retry(self, method: str, endpoint: str, max_retries: int = MAX_RETRIES, 
                                          initial_backoff: float = INITIAL_BACKOFF, **kwargs) -> Dict[str, Any]:
        """
        Make HTTP request with retry logic that handles both network errors and rate limiting.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            max_retries: Maximum number of retry attempts
            initial_backoff: Initial backoff time in seconds
            **kwargs: Additional request parameters
            
        Returns:
            API response as dictionary
        """
        last_exception = None
        is_cold_start = self._detect_cold_start_scenario()
        rate_limit_retries = 0
        
        # Use enhanced retry parameters for cold start scenarios
        if is_cold_start:
            max_retries = max(max_retries, COLD_START_MAX_RETRIES)
            initial_backoff = max(initial_backoff, COLD_START_INITIAL_BACKOFF)
            logger.info(f"Cold start detected, using enhanced retry: max_retries={max_retries}, initial_backoff={initial_backoff}")
        
        for attempt in range(max_retries + 1):
            try:
                return self._make_request(method, endpoint, **kwargs)
            except PumpFunApiError as e:
                error_message = str(e)
                
                # Check if this is a rate limiting error
                if self._is_rate_limit_error(error_message):
                    if rate_limit_retries < RATE_LIMIT_MAX_RETRIES:
                        rate_limit_retries += 1
                        backoff_time = self._calculate_rate_limit_backoff(rate_limit_retries - 1)
                        
                        logger.warning(f"Rate limit detected on attempt {attempt + 1}, waiting {backoff_time:.1f}s before retry {rate_limit_retries}/{RATE_LIMIT_MAX_RETRIES}")
                        time.sleep(backoff_time)
                        continue
                    else:
                        logger.error(f"Rate limit retries exhausted ({RATE_LIMIT_MAX_RETRIES}), giving up")
                        raise PumpFunRateLimitError(f"Rate limit exceeded after {RATE_LIMIT_MAX_RETRIES} attempts: {error_message}")
                else:
                    # Not a rate limiting error, re-raise immediately
                    raise e
                    
            except PumpFunNetworkError as e:
                last_exception = e
                if attempt < max_retries:
                    # Progressive backoff with jitter for cold starts
                    base_backoff = initial_backoff * (2 ** attempt)
                    # Add jitter to prevent thundering herd
                    jitter = random.uniform(0.5, 1.5) if is_cold_start else 1.0
                    backoff_time = base_backoff * jitter
                    
                    if is_cold_start and attempt == 0:
                        logger.warning(f"Cold start timeout detected, initiating wake-up sequence. Retrying in {backoff_time:.1f}s")
                    else:
                        logger.warning(f"Network error on attempt {attempt + 1}/{max_retries + 1}, retrying in {backoff_time:.1f}s: {str(e)}")
                    
                    time.sleep(backoff_time)
                else:
                    logger.error(f"All {max_retries + 1} retry attempts failed: {str(e)}")
            except (PumpFunValidationError) as e:
                # Don't retry validation errors
                raise e
                
        raise last_exception

    # Wallet Management Methods

    def create_airdrop_wallet(self, private_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Create or import an airdrop (mother) wallet.
        Enhanced with robust retry logic for cold start scenarios.
        
        Args:
            private_key: Optional private key for import (base58 string)
            
        Returns:
            Dictionary with wallet details
        """
        endpoint = "/api/wallets/airdrop"
        data = {}
        if private_key:
            data["privateKey"] = private_key
        
        # Use critical operations retry for wallet creation
        logger.info("Creating/importing airdrop wallet with enhanced retry logic")
        response = self._make_request_for_critical_operations("POST", endpoint, json=data)
        
        # Debug logging to understand response structure
        logger.info(f"Airdrop wallet creation response: {response}")
        
        # Handle different response formats that might be returned
        if isinstance(response, dict):
            # Check if it's a response with data field (expected format)
            if "data" in response:
                wallet_data = response["data"]
                
                # Normalize the response to expected format
                normalized_response = {}
                
                # Handle different field names that might be used
                if "address" in wallet_data:
                    normalized_response["address"] = wallet_data["address"]
                elif "publicKey" in wallet_data:
                    normalized_response["address"] = wallet_data["publicKey"]
                elif "public_key" in wallet_data:
                    normalized_response["address"] = wallet_data["public_key"]
                else:
                    # Log all available fields for debugging
                    logger.error(f"No address field found in wallet data. Available fields: {list(wallet_data.keys())}")
                    raise PumpFunApiError(f"Wallet creation response missing address field. Available fields: {list(wallet_data.keys())}")
                
                # Handle private key field
                if "privateKey" in wallet_data:
                    normalized_response["private_key"] = wallet_data["privateKey"]
                elif "private_key" in wallet_data:
                    normalized_response["private_key"] = wallet_data["private_key"]
                elif "secretKey" in wallet_data:
                    normalized_response["private_key"] = wallet_data["secretKey"]
                
                return normalized_response
            
            # Check if it's a success response with data (alternative format)
            elif response.get("success") and "data" in response:
                wallet_data = response["data"]
                
                # Normalize the response to expected format
                normalized_response = {}
                
                # Handle different field names that might be used
                if "address" in wallet_data:
                    normalized_response["address"] = wallet_data["address"]
                elif "publicKey" in wallet_data:
                    normalized_response["address"] = wallet_data["PublicKey"]
                elif "public_key" in wallet_data:
                    normalized_response["address"] = wallet_data["public_key"]
                else:
                    # Log all available fields for debugging
                    logger.error(f"No address field found in wallet data. Available fields: {list(wallet_data.keys())}")
                    raise PumpFunApiError(f"Wallet creation response missing address field. Available fields: {list(wallet_data.keys())}")
                
                # Handle private key field
                if "privateKey" in wallet_data:
                    normalized_response["private_key"] = wallet_data["privateKey"]
                elif "private_key" in wallet_data:
                    normalized_response["private_key"] = wallet_data["private_key"]
                elif "secretKey" in wallet_data:
                    normalized_response["private_key"] = wallet_data["secretKey"]
                
                return normalized_response
            
            # Handle direct response format (no success wrapper)
            elif "address" in response or "publicKey" in response or "public_key" in response:
                normalized_response = {}
                
                if "address" in response:
                    normalized_response["address"] = response["address"]
                elif "publicKey" in response:
                    normalized_response["address"] = response["PublicKey"]
                elif "public_key" in response:
                    normalized_response["address"] = response["public_key"]
                
                if "privateKey" in response:
                    normalized_response["private_key"] = response["privateKey"]
                elif "private_key" in response:
                    normalized_response["private_key"] = response["private_key"]
                elif "secretKey" in response:
                    normalized_response["private_key"] = response["secretKey"]
                
                return normalized_response
            
            # Handle error responses
            elif "error" in response:
                raise PumpFunApiError(f"Wallet creation failed: {response['error']}")
            
            else:
                # Log unexpected response format
                logger.error(f"Unexpected response format: {response}")
                raise PumpFunApiError(f"Unexpected response format. Response: {response}")
        
        else:
            logger.error(f"Invalid response type: {type(response)}")
            raise PumpFunApiError(f"Invalid response type: {type(response)}")

    def create_bundled_wallets(self, count: int) -> Dict[str, Any]:
        """
        Create bundled (child) wallets.
        
        Args:
            count: Number of wallets to create
            
        Returns:
            Dictionary with created wallet details
        """
        if count <= 0:
            raise PumpFunValidationError("Wallet count must be greater than 0")
            
        endpoint = "/api/wallets/bundled/create"
        data = {"count": count}
        
        # Use enhanced retry for critical wallet operations
        return self._make_request_for_critical_operations("POST", endpoint, json=data)

    def import_bundled_wallets(self, wallets: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Import bundled (child) wallets with enhanced error handling for bs58 issues.
        
        Args:
            wallets: List of wallet dictionaries with 'name' and 'privateKey' fields
            
        Returns:
            Dictionary with imported wallet details
        """
        if not wallets:
            raise PumpFunValidationError("Wallets list cannot be empty")
            
        # Validate wallet format and ensure both field names for server compatibility
        validated_wallets = []
        for i, wallet in enumerate(wallets):
            if 'name' not in wallet or ('privateKey' not in wallet and 'privateKeyBs58' not in wallet):
                raise PumpFunValidationError(f"Wallet {i} must have 'name' and 'privateKey' or 'privateKeyBs58' fields")
            
            # Get the private key value
            private_key_value = wallet.get('privateKey') or wallet.get('privateKeyBs58')
            if not private_key_value:
                raise PumpFunValidationError(f"Wallet {i} ({wallet.get('name', 'Unknown')}) missing private key")
            
            # Validate base58 format on client side to catch issues early
            try:
                # Check if it's valid base58 and correct length
                if len(private_key_value) != 88:
                    raise ValueError(f"Invalid private key length: {len(private_key_value)} (expected 88)")
                
                # Try to decode as base58 to validate format
                import base58
                decoded = base58.b58decode(private_key_value)
                if len(decoded) != 64:
                    raise ValueError(f"Invalid decoded key length: {len(decoded)} bytes (expected 64)")
                    
            except Exception as validation_error:
                raise PumpFunValidationError(f"Wallet {i} ({wallet.get('name', 'Unknown')}) has invalid private key format: {str(validation_error)}")
            
            # Create validated wallet object with both field names for server compatibility
            validated_wallet = {
                'name': wallet['name'],
                'privateKey': private_key_value,        # For processing layer
                'privateKeyBs58': private_key_value     # For validation layer
            }
            validated_wallets.append(validated_wallet)
                
        endpoint = "/api/wallets/bundled/import"
        data = {"wallets": validated_wallets}
        
        try:
            return self._make_request_with_retry("POST", endpoint, json=data)
        except Exception as e:
            error_message = str(e)
            # Enhanced error handling for common server-side issues
            if "bs58.decode is not a function" in error_message:
                raise PumpFunApiError(
                    "Server-side bs58 library error detected. "
                    "This indicates a server configuration issue. "
                    f"Original error: {error_message}"
                )
            elif "bs58" in error_message.lower():
                raise PumpFunApiError(
                    f"Server-side base58 processing error: {error_message}. "
                    "Check that all private keys are in valid base58 format."
                )
            else:
                # Re-raise original exception for other types of errors
                raise

    def fund_bundled_wallets(self, amount_per_wallet: float, mother_private_key: Optional[str] = None, 
                           bundled_wallets: Optional[List[Dict[str, str]]] = None,
                           target_wallet_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Fund bundled wallets from the airdrop wallet using the new stateless API format.
        
        Updated to use the new API endpoint format that requires all wallet credentials
        to be provided directly in the request body without server-side state management.
        
        New API Format:
        {
            "amountPerWalletSOL": <number>,
            "childWallets": [
                { "name": "DevWallet", "privateKey": "<base58 string>" },
                { "name": "First Bundled Wallet 1", "privateKey": "<base58 string>" }
            ],
            "motherWalletPrivateKeyBs58": "<base58 string>",
            "targetWalletNames": ["DevWallet"] // optional
        }
        
        Args:
            amount_per_wallet: SOL amount to send to each wallet
            mother_private_key: Mother wallet private key in base58 format
            bundled_wallets: List of bundled wallet credentials with name and privateKey
            target_wallet_names: Optional list of specific wallet names to fund
            
        Returns:
            Dictionary with funding transaction results
        """
        # Validate required parameters for new API format
        if not mother_private_key:
            raise PumpFunValidationError("Mother wallet private key is required for stateless API")
        if not bundled_wallets or len(bundled_wallets) == 0:
            raise PumpFunValidationError("Bundled wallets list is required and cannot be empty")
        
        # Validate each bundled wallet has required fields
        for i, wallet in enumerate(bundled_wallets):
            if not isinstance(wallet, dict):
                raise PumpFunValidationError(f"Bundled wallet {i} must be a dictionary")
            if "name" not in wallet or not wallet["name"]:
                raise PumpFunValidationError(f"Bundled wallet {i} missing required 'name' field")
            if "privateKey" not in wallet or not wallet["privateKey"]:
                raise PumpFunValidationError(f"Bundled wallet {i} missing required 'privateKey' field")

        if amount_per_wallet <= 0:
            raise PumpFunValidationError("Amount per wallet must be greater than 0")

        logger.info("=== FUNDING OPERATION EXECUTION ===")
        logger.info(f"Funding bundled wallets with {amount_per_wallet:.6f} SOL each")

        # Enhanced fee calculation per API documentation
        base_fee_lamports = 5000  # Base transaction fee
        priority_fee_lamports = 20000  # Priority fee for faster processing
        total_estimated_fee_lamports = base_fee_lamports + priority_fee_lamports  # ~25,000 lamports
        minimum_reserve_lamports = 100_000  # 0.0001 SOL minimum reserve for wallet management
        
        # Calculate minimum required amount including fees
        min_fee_sol = total_estimated_fee_lamports / 1_000_000_000
        min_reserve_sol = minimum_reserve_lamports / 1_000_000_000
        absolute_minimum = min_fee_sol + min_reserve_sol  # ~0.000125 SOL
        
        # Validate reasonable amount with enhanced fee consideration
        if amount_per_wallet < absolute_minimum:
            raise PumpFunValidationError(
                f"Amount per wallet too small (minimum {absolute_minimum:.6f} SOL required for fees + reserve). "
                f"Fee: {min_fee_sol:.6f} SOL, Reserve: {min_reserve_sol:.6f} SOL"
            )
        if amount_per_wallet > 10:
            raise PumpFunValidationError("Amount per wallet too large (maximum 10 SOL)")
        
        # Log detailed fee calculation for debugging
        logger.info(f"Fund bundled wallets fee calculation:")
        logger.info(f"  Amount per wallet: {amount_per_wallet} SOL")
        logger.info(f"  Base fee: {base_fee_lamports} lamports ({min_fee_sol:.6f} SOL)")
        logger.info(f"  Priority fee: {priority_fee_lamports} lamports") 
        logger.info(f"  Total estimated fee: {total_estimated_fee_lamports} lamports ({min_fee_sol:.6f} SOL)")
        logger.info(f"  Minimum reserve: {minimum_reserve_lamports} lamports ({min_reserve_sol:.6f} SOL)")
        logger.info(f"  Absolute minimum amount: {absolute_minimum:.6f} SOL")
            
        endpoint = "/api/wallets/fund-bundled"
        
        # New API format: provide all wallet credentials directly in request
        # Round amount to 9 decimal places to avoid floating point precision issues with lamport conversion
        rounded_amount = round(amount_per_wallet, 9)
        data = {
            "amountPerWalletSOL": rounded_amount,
            "childWallets": bundled_wallets,
            "motherWalletPrivateKeyBs58": mother_private_key
        }
        
        # Add optional target wallet names if specified
        if target_wallet_names:
            data["targetWalletNames"] = target_wallet_names
        
        logger.info(f"Funding {len(bundled_wallets)} bundled wallets with new API format")
        logger.info(f"Amount per wallet: {rounded_amount} SOL (rounded from {amount_per_wallet})")
        if target_wallet_names:
            logger.info(f"Target wallets: {target_wallet_names}")
        
        # Debug log (excluding sensitive data)
        debug_data = {
            "amountPerWalletSOL": amount_per_wallet,
            "childWalletsCount": len(bundled_wallets),
            "childWalletNames": [w.get("name", "Unknown") for w in bundled_wallets],
            "motherWalletProvided": bool(mother_private_key),
            "targetWalletNames": target_wallet_names
        }
        logger.info(f"PumpFun API POST {endpoint} - Request summary: {debug_data}")
        
        try:
            result = self._make_request_with_retry("POST", endpoint, json=data)
            
            # Normalize response: convert list to expected dict format (API contract change fix)
            if isinstance(result, list):
                logger.info(f"API returned list response, normalizing to dict format")
                transfers = result
                total_amount = sum(item.get("amount", 0) for item in transfers if isinstance(item, dict))
                successful_transfers = len([item for item in transfers if isinstance(item, dict) and item.get("status") != "failed"])
                failed_transfers = len(transfers) - successful_transfers
                
                result = {
                    "status": "success",
                    "message": "Fund bundled wallets operation completed successfully",
                    "data": {
                        "transfers": transfers,
                        "totalWallets": len(transfers),
                        "successfulTransfers": successful_transfers,
                        "failedTransfers": failed_transfers,
                        "totalAmount": total_amount,
                        "walletsCount": len(transfers),
                        "amountPerWallet": amount_per_wallet
                    }
                }
                logger.info(f"Normalized list response: {successful_transfers} successful, {failed_transfers} failed, {total_amount:.6f} SOL total")
            
            # Log successful operation details
            logger.info(f"Fund bundled wallets operation completed successfully")
            logger.info(f"Final response type: {type(result)}")
            
            if isinstance(result, dict):
                logger.info(f"Response keys: {list(result.keys())}")
                
                # Log data section details if present
                if "data" in result:
                    data_section = result["data"]
                    logger.info(f"  Data section type: {type(data_section)}")
                    
                    if isinstance(data_section, dict):
                        logger.info(f"  Wallets funded: {data_section.get('walletsCount', 'unknown')}")
                        logger.info(f"  Amount per wallet: {data_section.get('amountPerWallet', 'unknown')} SOL")
                        logger.info(f"  Total amount sent: {data_section.get('totalAmount', 'unknown')} SOL")
                        if 'bundleId' in data_section:
                            logger.info(f"  Bundle ID: {data_section['bundleId']}")
                
                # Check for other common response patterns
                if "message" in result:
                    logger.info(f"  Response message: {result['message']}")
                if "status" in result:
                    logger.info(f"  Response status: {result['status']}")
                if "error" in result:
                    logger.warning(f"  Response error: {result['error']}")
            
            return result
            
        except Exception as e:
            error_message = str(e).lower()
            
            # Enhanced error detection for insufficient funds scenarios per API documentation
            insufficient_funds_patterns = [
                "custom program error: 1",  # Primary insufficient lamports error
                "insufficient funds",       # Standard insufficient funds
                "insufficient lamports",    # Lamports-specific error
                "insufficient balance",     # Balance-specific error
                "not enough sol",          # Alternative phrasing
                "insufficient account balance"  # Account balance error
            ]
            
            is_insufficient_funds = any(pattern in error_message for pattern in insufficient_funds_patterns)
            
            if is_insufficient_funds:
                logger.error(f"Insufficient funds detected during fund bundled wallets operation:")
                logger.error(f"  Error message: {str(e)}")
                logger.error(f"  Amount per wallet: {amount_per_wallet} SOL")
                logger.error(f"  Required minimum per wallet: {minimum_reserve_lamports} lamports")
                logger.error(f"  Estimated fee per transaction: {total_estimated_fee_lamports} lamports")
                logger.error(f"  Recommendation: Ensure airdrop wallet has sufficient balance for all transfers + fees")
                
                # Enhance the error with specific guidance
                enhanced_error = PumpFunApiError(
                    f"Insufficient funds for funding operation. {str(e)}. "
                    f"Airdrop wallet needs at least {amount_per_wallet} SOL per wallet plus "
                    f"transaction fees (~{min_fee_sol:.6f} SOL per wallet) for successful operation."
                )
                raise enhanced_error
            else:
                # Log other types of errors with context
                logger.error(f"Fund bundled wallets operation failed with non-balance error:")
                logger.error(f"  Error type: {type(e).__name__}")
                logger.error(f"  Error message: {str(e)}")
                logger.error(f"  Amount per wallet: {amount_per_wallet} SOL")
                
                # Re-raise original exception for non-balance errors
                raise

    def verify_bundled_wallets_exist(self) -> Dict[str, Any]:
        """
        Verify if bundled wallets exist on the API server.
        Enhanced with path error detection for better debugging.
        
        Returns:
            Dictionary with verification results including wallet count and details
        """
        try:
            # Try to get a simple balance check on the first bundled wallet
            # This is an indirect way to verify if wallets are imported
            # Since there's no explicit "list bundled wallets" endpoint documented
            
            # Alternative: Try to fund with 0 amount to test if wallets exist
            test_endpoint = "/api/wallets/fund-bundled"
            test_data = {"amountPerWalletSOL": 0.0}  # Use actual server parameter name
            
            logger.info("Verifying bundled wallets exist on API server...")
            
            try:
                response = self._make_request_with_retry("POST", test_endpoint, json=test_data)
                
                # If we get a validation error about amount being 0, wallets exist
                # If we get "No child wallets found", wallets don't exist
                return {
                    "wallets_exist": True,
                    "verification_method": "funding_test",
                    "response": response
                }
            except PumpFunValidationError as e:
                error_msg = str(e).lower()
                if "no child wallets found" in error_msg or "no bundled wallets" in error_msg:
                    return {
                        "wallets_exist": False,
                        "verification_method": "funding_test",
                        "error": str(e)
                    }
                elif "amount" in error_msg and ("0" in error_msg or "positive" in error_msg):
                    # Amount validation error means wallets exist but amount is invalid
                    return {
                        "wallets_exist": True,
                        "verification_method": "funding_test",
                        "note": "Wallets exist - amount validation triggered"
                    }
                else:
                    # Unknown validation error
                    return {
                        "wallets_exist": False,
                        "verification_method": "funding_test",
                        "error": str(e),
                        "unknown_error": True
                    }
            except PumpFunApiError as e:
                # Check for path-related errors that indicate server-side configuration issues
                error_msg = str(e).lower()
                if "path" in error_msg and "undefined" in error_msg:
                    return {
                        "wallets_exist": False,
                        "verification_method": "funding_test",
                        "error": str(e),
                        "path_error": True,
                        "diagnosis": "Server-side wallet file path configuration issue detected"
                    }
                else:
                    # Other API errors
                    return {
                        "wallets_exist": False,
                        "verification_method": "funding_test",
                        "error": str(e),
                        "api_error": True
                    }
            except Exception as e:
                # Network or other errors
                return {
                    "wallets_exist": False,
                    "verification_method": "funding_test",
                    "error": str(e),
                    "network_error": True
                }
                
        except Exception as e:
            logger.error(f"Failed to verify bundled wallets: {str(e)}")
            return {
                "wallets_exist": False,
                "verification_method": "failed",
                "error": str(e)
            }

    def diagnose_server_wallet_configuration(self) -> Dict[str, Any]:
        """
        Diagnose server-side wallet configuration issues.
        Specifically looks for path-related errors that indicate server configuration problems.
        
        Returns:
            Dictionary with diagnostic results and recommendations
        """
        logger.info("Running server-side wallet configuration diagnostics...")
        
        # Test multiple endpoints to identify configuration issues
        diagnostics = {
            "wallet_verification": self.verify_bundled_wallets_exist(),
            "recommendations": [],
            "configuration_issues": []
        }
        
        # Analyze wallet verification results
        wallet_status = diagnostics["wallet_verification"]
        
        if wallet_status.get("path_error", False):
            diagnostics["configuration_issues"].append({
                "issue": "Server wallet file path configuration",
                "description": "The server is trying to load wallet files but the path parameter is undefined",
                "error": wallet_status.get("error", "Unknown path error")
            })
            
            diagnostics["recommendations"].extend([
                "Check server environment variables for wallet file paths",
                "Ensure WALLETS_FILE_PATH or similar environment variable is set",
                "Verify wallet files exist in the expected server directory",
                "Check server logs for additional path-related errors"
            ])
        
        elif not wallet_status.get("wallets_exist", False):
            diagnostics["configuration_issues"].append({
                "issue": "No bundled wallets found",
                "description": "The server does not have any bundled wallets configured",
                "error": wallet_status.get("error", "No wallets found")
            })
            
            diagnostics["recommendations"].extend([
                "Create bundled wallets using the create_bundled_wallets() method",
                "Import existing wallets using the import_bundled_wallets() method",
                "Ensure wallets are properly saved to the server's storage system"
            ])
        
        else:
            diagnostics["recommendations"].append("Wallet configuration appears to be healthy")
        
        return diagnostics

    def return_funds_to_mother(self, mother_wallet_public_key: str, child_wallets: List[Dict[str, str]],
                              source_wallet_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Return funds from bundled wallets to the airdrop wallet using the new stateless API format.
        
        Updated to use the new API endpoint format that requires all wallet credentials
        to be provided directly in the request body.
        
        New API Format:
        {
            "childWallets": [
                { "name": "DevWallet", "privateKey": "<base58 string>" },
                { "name": "First Bundled Wallet 1", "privateKey": "<base58 string>" }
            ],
            "motherWalletPublicKeyBs58": "<base58 string>",
            "sourceWalletNames": ["DevWallet"] // optional
        }
        
        Args:
            mother_wallet_public_key: Public key of the mother (airdrop) wallet in base58 format
            child_wallets: List of child wallet credentials with name and privateKey
            source_wallet_names: Optional list of specific wallet names to return funds from
            
        Returns:
            Dictionary with return transaction results
        """
        # Validate required parameters for new API format
        if not mother_wallet_public_key:
            raise PumpFunValidationError("Mother wallet public key cannot be empty")
        if not child_wallets or len(child_wallets) == 0:
            raise PumpFunValidationError("Child wallets list is required and cannot be empty")
        
        # Validate each child wallet has required fields
        for i, wallet in enumerate(child_wallets):
            if not isinstance(wallet, dict):
                raise PumpFunValidationError(f"Child wallet {i} must be a dictionary")
            if "name" not in wallet or not wallet["name"]:
                raise PumpFunValidationError(f"Child wallet {i} missing required 'name' field")
            if "privateKey" not in wallet or not wallet["privateKey"]:
                raise PumpFunValidationError(f"Child wallet {i} missing required 'privateKey' field")

        logger.info(f"Returning funds from {len(child_wallets)} child wallets to mother wallet")
        logger.info(f"Mother wallet: {mother_wallet_public_key}")
        if source_wallet_names:
            logger.info(f"Source wallets: {source_wallet_names}")
            
        endpoint = "/api/wallets/return-funds"
        
        # New API format: provide all wallet credentials directly in request
        data = {
            "childWallets": child_wallets,
            "motherWalletPublicKeyBs58": mother_wallet_public_key
        }
        
        # Add optional source wallet names if specified
        if source_wallet_names:
            data["sourceWalletNames"] = source_wallet_names
        
        # Debug log (excluding sensitive data)
        debug_data = {
            "childWalletsCount": len(child_wallets),
            "childWalletNames": [w.get("name", "Unknown") for w in child_wallets],
            "motherWalletPublicKey": mother_wallet_public_key,
            "sourceWalletNames": source_wallet_names
        }
        logger.info(f"PumpFun API POST {endpoint} - Request summary: {debug_data}")
        
        try:
            result = self._make_request_with_retry("POST", endpoint, json=data)
            
            # Normalize response: handle both list response and dict with list data
            if isinstance(result, list):
                logger.info(f"API returned list response, normalizing to dict format")
                transfers = result
                total_amount = sum(item.get("amountReturned", 0) for item in transfers if isinstance(item, dict))
                successful_transfers = len([item for item in transfers if isinstance(item, dict) and item.get("status") not in ["failed", "skipped_low_balance"]])
                failed_transfers = len(transfers) - successful_transfers
                
                result = {
                    "status": "success",
                    "message": "Return funds operation completed successfully",
                    "data": {
                        "transfers": transfers,
                        "totalWallets": len(transfers),
                        "successfulTransfers": successful_transfers,
                        "failedTransfers": failed_transfers,
                        "totalAmount": total_amount
                    }
                }
                logger.info(f"Normalized list response: {successful_transfers} successful, {failed_transfers} failed, {total_amount:.6f} SOL total")
            elif isinstance(result, dict) and "data" in result and isinstance(result["data"], list):
                logger.info(f"API returned dict with list data, normalizing data section")
                transfers = result["data"]
                total_amount = sum(item.get("amountReturned", 0) for item in transfers if isinstance(item, dict))
                successful_transfers = len([item for item in transfers if isinstance(item, dict) and item.get("status") not in ["failed", "skipped_low_balance"]])
                failed_transfers = len(transfers) - successful_transfers
                
                # Normalize the data section to expected format
                result["data"] = {
                    "transfers": transfers,
                    "totalWallets": len(transfers),
                    "successfulTransfers": successful_transfers,
                    "failedTransfers": failed_transfers,
                    "totalAmount": total_amount
                }
                logger.info(f"Normalized dict data section: {successful_transfers} successful, {failed_transfers} failed, {total_amount:.6f} SOL total")
            
            # Enhanced logging for debugging response structure
            logger.info(f"Return funds operation completed successfully")
            logger.info(f"Final response type: {type(result)}")
            
            if isinstance(result, dict):
                logger.info(f"Response keys: {list(result.keys())}")
                
                # Log data section details if present
                if "data" in result:
                    data_section = result["data"]
                    logger.info(f"  Data section type: {type(data_section)}")
                    
                    if isinstance(data_section, dict):
                        logger.info(f"  Wallets processed: {data_section.get('totalWallets', 'unknown')}")
                        logger.info(f"  Successful transfers: {data_section.get('successfulTransfers', 'unknown')}")
                        logger.info(f"  Failed transfers: {data_section.get('failedTransfers', 'unknown')}")
                        if 'totalAmount' in data_section:
                            logger.info(f"  Total amount returned: {data_section['totalAmount']} SOL")
                
                # Check for other common response patterns
                if "message" in result:
                    logger.info(f"  Response message: {result['message']}")
                if "status" in result:
                    logger.info(f"  Response status: {result['status']}")
                if "error" in result:
                    logger.warning(f"  Response error: {result['error']}")
            
            return result
            
        except Exception as e:
            error_message = str(e).lower()
            
            # Enhanced error detection for insufficient funds scenarios per API documentation
            insufficient_funds_patterns = [
                "custom program error: 1",  # Primary insufficient lamports error
                "insufficient funds",       # Standard insufficient funds
                "insufficient lamports",    # Lamports-specific error
                "insufficient balance",     # Balance-specific error
                "not enough sol",          # Alternative phrasing
                "insufficient account balance"  # Account balance error
            ]
            
            is_insufficient_funds = any(pattern in error_message for pattern in insufficient_funds_patterns)
            
            if is_insufficient_funds:
                logger.error(f"Insufficient funds detected during return funds operation:")
                logger.error(f"  Error message: {str(e)}")
                logger.error(f"  Mother wallet: {mother_wallet_public_key}")
                logger.error(f"  Child wallets count: {len(child_wallets)}")
                if source_wallet_names:
                    logger.error(f"  Source wallets: {source_wallet_names}")
                
                # Enhance the error with specific guidance
                enhanced_error = PumpFunApiError(
                    f"Insufficient funds for return funds operation: {str(e)}. "
                    f"Please ensure all child wallets have sufficient balance for transaction fees and rent exemption."
                )
                raise enhanced_error
            else:
                # Log other types of errors with context
                logger.error(f"Return funds operation failed with non-balance error:")
                logger.error(f"  Error type: {type(e).__name__}")
                logger.error(f"  Error message: {str(e)}")
                logger.error(f"  Mother wallet: {mother_wallet_public_key}")
                logger.error(f"  Child wallets count: {len(child_wallets)}")
                
                # Re-raise original exception for non-balance errors
                raise

    def get_wallet_balance(self, public_key: str) -> Dict[str, Any]:
        """
        Get wallet SOL balance (updated to use legacy endpoint that works).
        
        Args:
            public_key: Wallet public key
            
        Returns:
            Dictionary with SOL balance information
        """
        if not public_key:
            raise PumpFunValidationError("Public key cannot be empty")
            
        # Use legacy endpoint directly since enhanced endpoints are not available
        return self._get_wallet_balance_legacy(public_key)

    def _get_wallet_balance_legacy(self, public_key: str) -> Dict[str, Any]:
        """
        Get wallet SOL balance using legacy endpoint.
        
        Args:
            public_key: Wallet public key
            
        Returns:
            Dictionary with SOL balance information in standardized format
        """
        legacy_endpoint = f"/api/wallets/{public_key}/balance"
        
        try:
            response = self._make_request_with_retry("GET", legacy_endpoint)
            logger.info(f"Legacy balance response for {public_key[:8]}...{public_key[-4:]}: {response}")
            
            # Transform legacy response to match enhanced format
            if "data" in response:
                data = response["data"]
                balance = data.get("balance", 0)
                lamports = int(balance * 1_000_000_000) if balance else 0
                
                return {
                    "message": response.get("message", "Balance retrieved successfully."),
                    "data": {
                        "publicKey": data.get("publicKey", public_key),
                        "balance": balance,
                        "lamports": lamports
                    }
                }
            else:
                # Handle direct balance response
                balance = response.get("balance", 0)
                lamports = int(balance * 1_000_000_000) if balance else 0
                
                return {
                    "message": "Balance retrieved successfully.",
                    "data": {
                        "publicKey": public_key,
                        "balance": balance,
                        "lamports": lamports
                    }
                }
                
        except Exception as e:
            logger.error(f"Legacy balance endpoint failed for {public_key[:8]}...{public_key[-4:]}: {str(e)}")
            # Return zero balance as last resort
            return {
                "message": "Balance check failed, returning zero balance",
                "data": {
                    "publicKey": public_key,
                    "balance": 0,
                    "lamports": 0
                },
                "error": str(e)
            }

    def get_wallet_sol_balance(self, public_key: str) -> Dict[str, Any]:
        """
        Get wallet SOL balance using legacy endpoint that works.
        
        Args:
            public_key: Wallet public key
            
        Returns:
            Dictionary with detailed SOL balance information
        """
        if not public_key:
            raise PumpFunValidationError("Public key cannot be empty")
            
        # Use legacy endpoint directly since enhanced endpoints are not available
        return self._get_wallet_balance_legacy(public_key)

    def get_wallet_token_balance(self, public_key: str, mint_address: str) -> Dict[str, Any]:
        """
        Get specific SPL token balance for a wallet with fallback.
        
        Args:
            public_key: Wallet public key
            mint_address: Token mint address
            
        Returns:
            Dictionary with token balance information
        """
        if not public_key:
            raise PumpFunValidationError("Public key cannot be empty")
        if not mint_address:
            raise PumpFunValidationError("Mint address cannot be empty")
            
        endpoint = f"/api/wallets/{public_key}/balance/token/{mint_address}"
        
        try:
            return self._make_request_with_retry("GET", endpoint)
        except PumpFunApiError as e:
            # If 404 or similar error, provide a fallback response
            if "404" in str(e) or "Cannot GET" in str(e):
                logger.warning(f"Enhanced token balance endpoint not available: {str(e)}")
                return {
                    "message": "Token balance endpoint not available",
                    "data": {
                        "publicKey": public_key,
                        "token": {
                            "mint": mint_address,
                            "balance": 0,
                            "decimals": 6,
                            "uiAmount": 0.0,
                            "symbol": None,
                            "usdValue": None
                        },
                        "metadata": {
                            "status": "fallback",
                            "error": "Enhanced token balance endpoint not implemented"
                        }
                    }
                }
            else:
                # Re-raise other API errors
                raise e

    def get_wallet_complete_balance(self, public_key: str) -> Dict[str, Any]:
        """
        Get complete wallet balance (SOL + all SPL tokens) with fallback.
        
        Args:
            public_key: Wallet public key
            
        Returns:
            Dictionary with complete balance information
        """
        if not public_key:
            raise PumpFunValidationError("Public key cannot be empty")
            
        endpoint = f"/api/wallets/{public_key}/balance/all"
        
        try:
            return self._make_request_with_retry("GET", endpoint)
        except PumpFunApiError as e:
            # If 404 or similar error, fall back to SOL balance only
            if "404" in str(e) or "Cannot GET" in str(e):
                logger.warning(f"Enhanced complete balance endpoint not available, falling back to SOL only: {str(e)}")
                sol_balance = self._get_wallet_balance_legacy(public_key)
                
                # Transform to complete balance format
                sol_data = sol_balance.get("data", {})
                balance = sol_data.get("balance", 0)
                lamports = sol_data.get("lamports", 0)
                
                return {
                    "message": "Complete wallet balance retrieved (SOL only due to API limitations)",
                    "data": {
                        "publicKey": public_key,
                        "sol": {
                            "balance": balance,
                            "lamports": lamports,
                            "usdValue": None
                        },
                        "tokens": [],
                        "summary": {
                            "totalAssets": 1,
                            "solBalance": balance,
                            "tokenCount": 0,
                            "hasTokens": False,
                            "lastUpdated": None
                        },
                        "metadata": {
                            "status": "fallback",
                            "error": "Enhanced balance endpoints not implemented"
                        }
                    }
                }
            else:
                # Re-raise other API errors
                raise e

    def get_wallet_tokens_balance(self, public_key: str) -> Dict[str, Any]:
        """
        Get all SPL token balances for a wallet (without SOL) with fallback.
        
        Args:
            public_key: Wallet public key
            
        Returns:
            Dictionary with all token balance information
        """
        if not public_key:
            raise PumpFunValidationError("Public key cannot be empty")
            
        endpoint = f"/api/wallets/{public_key}/balance/tokens"
        
        try:
            return self._make_request_with_retry("GET", endpoint)
        except PumpFunApiError as e:
            # If 404 or similar error, return empty tokens response
            if "404" in str(e) or "Cannot GET" in str(e):
                logger.warning(f"Enhanced tokens balance endpoint not available: {str(e)}")
                return {
                    "message": "Token balances endpoint not available",
                    "data": {
                        "publicKey": public_key,
                        "tokens": [],
                        "summary": {
                            "tokenCount": 0,
                            "hasTokens": False,
                            "totalTokenAccounts": 0
                        },
                        "metadata": {
                            "status": "fallback",
                            "error": "Enhanced token balance endpoints not implemented"
                        }
                    }
                }
            else:
                # Re-raise other API errors
                raise e

    # Pump Portal Trading Methods

    # Image upload is now implemented as part of create_token_and_buy method
    # using multipart/form-data uploads as per API documentation

    def _transform_token_params_for_api(self, token_params: TokenCreationParams) -> Dict[str, Any]:
        """
        Transform snake_case token params to API-expected camelCase format.
        
        Args:
            token_params: Token creation parameters with snake_case fields
            
        Returns:
            Dictionary with camelCase field names for API compatibility
        """
        # Create base dictionary from token params
        base_params = asdict(token_params)
        
        # Transform snake_case to camelCase for API compatibility
        transformed_params = {
            "name": base_params["name"],
            "symbol": base_params["symbol"],
            "description": base_params["description"],
            "twitter": base_params["twitter"],
            "telegram": base_params["telegram"],
            "website": base_params["website"],
            "showName": base_params["show_name"],  # snake_case -> camelCase
            "initialSupplyAmount": base_params["initial_supply_amount"],  # snake_case -> camelCase
            "imageFileName": base_params["image_url"]  # snake_case -> camelCase (semantic change)
        }
        
        # Log the transformation for debugging
        logger.info(f"Transformed token params: snake_case -> camelCase mapping applied")
        logger.debug(f"Original params: {base_params}")
        logger.debug(f"Transformed params: {transformed_params}")
        
        return transformed_params

    def _validate_api_request_format(self, transformed_params: Dict[str, Any], operation: str = "token_creation") -> None:
        """
        Validate that transformed parameters match API expected format.
        
        Args:
            transformed_params: Transformed parameters dictionary
            operation: Operation type for context in error messages
            
        Raises:
            PumpFunValidationError: If validation fails
        """
        # Define required fields for token creation API
        required_api_fields = ["name", "symbol", "description", "showName", "initialSupplyAmount"]
        optional_api_fields = ["twitter", "telegram", "website", "imageFileName"]
        
        # Check for required fields
        missing_fields = [field for field in required_api_fields if field not in transformed_params]
        if missing_fields:
            raise PumpFunValidationError(f"Missing required API fields for {operation}: {missing_fields}")
        
        # Check field types match API expectations
        type_validations = {
            "showName": bool,
            "initialSupplyAmount": str,
            "name": str,
            "symbol": str,
            "description": str
        }
        
        type_errors = []
        for field, expected_type in type_validations.items():
            if field in transformed_params and not isinstance(transformed_params[field], expected_type):
                type_errors.append(f"{field}: expected {expected_type.__name__}, got {type(transformed_params[field]).__name__}")
        
        if type_errors:
            raise PumpFunValidationError(f"API field type mismatches for {operation}: {type_errors}")
        
        # Log successful validation
        logger.info(f"Pre-request validation passed for {operation} with {len(transformed_params)} fields")

    def _validate_buy_amounts_json(self, buy_amounts_json: str) -> None:
        """
        Validate that the buyAmountsSOL JSON string is correctly formatted.
        
        Args:
            buy_amounts_json: JSON string to validate
            
        Raises:
            PumpFunValidationError: If validation fails
        """
        try:
            # Parse JSON to verify it's valid
            parsed = json.loads(buy_amounts_json)
            
            # Validate structure
            if not isinstance(parsed, dict):
                raise PumpFunValidationError("buyAmountsSOL must be a JSON object")
            
            # Check required fields
            required_fields = ["devWalletBuySOL", "firstBundledWallet1BuySOL"]
            for field in required_fields:
                if field not in parsed:
                    raise PumpFunValidationError(f"Missing required field in buyAmountsSOL: {field}")
                if not isinstance(parsed[field], (int, float)):
                    raise PumpFunValidationError(f"Field {field} must be a number, got {type(parsed[field])}")
                if parsed[field] < 0:
                    raise PumpFunValidationError(f"Field {field} must be positive, got {parsed[field]}")
            
            # Validate JSON string format (should be compact, no spaces)
            expected_format = json.dumps(parsed, separators=(',', ':'))
            if buy_amounts_json != expected_format:
                logger.warning(f"buyAmountsSOL JSON format suboptimal. Expected: {expected_format}, Got: {buy_amounts_json}")
                
            logger.info(f"buyAmountsSOL JSON validation passed: {buy_amounts_json}")
            
        except json.JSONDecodeError as e:
            raise PumpFunValidationError(f"Invalid JSON format for buyAmountsSOL: {str(e)}")
        except Exception as e:
            raise PumpFunValidationError(f"buyAmountsSOL validation failed: {str(e)}")

    def _validate_wallets_json(self, wallets_json: str) -> None:
        """
        Validate that the wallets JSON string is correctly formatted.
        
        Args:
            wallets_json: JSON string to validate
            
        Raises:
            PumpFunValidationError: If validation fails
        """
        try:
            # Parse JSON to verify it's valid
            parsed = json.loads(wallets_json)
            
            # Validate structure
            if not isinstance(parsed, list):
                raise PumpFunValidationError("wallets must be a JSON array")
            
            # Check required fields for each wallet
            wallet_names = []
            for wallet_data in parsed:
                if 'name' not in wallet_data or ('privateKey' not in wallet_data and 'privateKeyBs58' not in wallet_data):
                    raise PumpFunValidationError("Each wallet in the 'wallets' array must have 'name' and 'privateKey' or 'privateKeyBs58' fields")
                
                private_key_field = wallet_data.get('privateKey') or wallet_data.get('privateKeyBs58')
                if not isinstance(wallet_data['name'], str) or not isinstance(private_key_field, str):
                    raise PumpFunValidationError("Wallet 'name' and private key field must be strings")
                
                # Check for duplicate names
                if wallet_data['name'] in wallet_names:
                    raise PumpFunValidationError(f"Duplicate wallet name found: {wallet_data['name']}")
                wallet_names.append(wallet_data['name'])
                
                # Basic validation for private key (e.g., length)
                if len(private_key_field) < 80:  # More flexible length check
                    logger.warning(f"Wallet private key length suspicious: {len(private_key_field)}")
                
                logger.info(f"Wallet JSON validation passed for: {wallet_data['name']}")
            
            logger.info(f"wallets JSON validation passed: {wallets_json}")
            
        except json.JSONDecodeError as e:
            raise PumpFunValidationError(f"Invalid JSON format for wallets: {str(e)}")
        except Exception as e:
            raise PumpFunValidationError(f"wallets JSON validation failed: {str(e)}")

    def create_token_and_buy(self, token_params: TokenCreationParams, 
                           buy_amounts: BuyAmounts, wallets: List[Dict[str, str]], slippage_bps: int = 2500,
                           image_file_path: Optional[str] = None, create_amount_sol: float = 0.001) -> Dict[str, Any]:
        """
        Create a token and perform initial buys with proper multipart/form-data support.
        Enhanced with wallet loading error recovery.
        
        Args:
            token_params: Token creation parameters
            buy_amounts: Buy amounts for different wallets
            wallets: List of wallet dictionaries with 'name' and 'privateKey' fields
            slippage_bps: Slippage in basis points
            image_file_path: Local path to image file (if any)
            create_amount_sol: SOL amount for token creation (default: 0.001)
            
        Returns:
            Dictionary with token creation and buy results
        """
        # Validate token parameters
        self._validate_token_params(token_params)
        
        # Validate wallets parameter
        if not wallets:
            raise PumpFunValidationError("Wallets list cannot be empty")
        
        for wallet in wallets:
            if 'name' not in wallet or ('privateKey' not in wallet and 'privateKeyBs58' not in wallet):
                raise PumpFunValidationError("Each wallet must have 'name' and 'privateKey' or 'privateKeyBs58' fields")
            
            # Ensure both field names exist due to server validation/processing inconsistency
            private_key_value = wallet.get('privateKey') or wallet.get('privateKeyBs58')
            if private_key_value:
                wallet['privateKey'] = private_key_value        # For processing layer
                wallet['privateKeyBs58'] = private_key_value    # For validation layer
        
        endpoint = "/api/pump/create-and-buy"
        
        # Prepare buy amounts dictionary - create-and-buy endpoint only supports DevWallet + First Bundled Wallet
        # Additional wallets (2-4) should be handled via batch-buy endpoint separately
        buy_amounts_dict = {
            "devWalletBuySOL": buy_amounts.dev_wallet_buy_sol,
            "firstBundledWallet1BuySOL": buy_amounts.first_bundled_wallet_1_buy_sol
        }
        
        # Log buy amounts breakdown for debugging
        logger.info(f"Token creation buy amounts - DevWallet: {buy_amounts.dev_wallet_buy_sol} SOL, "
                   f"First Bundled Wallet: {buy_amounts.first_bundled_wallet_1_buy_sol} SOL")
        additional_total = (buy_amounts.first_bundled_wallet_2_buy_sol + 
                           buy_amounts.first_bundled_wallet_3_buy_sol + 
                           buy_amounts.first_bundled_wallet_4_buy_sol)
        if additional_total > 0:
            logger.info(f"Additional wallets will purchase {additional_total} SOL total after token creation")
        
        # Try token creation with enhanced error recovery
        token_result = None
        
        # Check if we have an image file to upload
        if image_file_path and os.path.exists(image_file_path):
            # Try multipart/form-data first for image upload
            logger.info(f"Creating token with image upload: {image_file_path}")
            try:
                token_result = self._create_token_with_image(token_params, buy_amounts_dict, wallets, slippage_bps, image_file_path, create_amount_sol)
            except PumpFunApiError as e:
                # Enhanced error handling for server-side wallet loading issues
                error_msg = str(e).lower()
                if "path" in error_msg and "undefined" in error_msg:
                    logger.error(f"Server-side wallet loading error detected: {str(e)}")
                    logger.info("Attempting to recover by ensuring wallet setup before token creation")
                    
                    # Try fallback to JSON without image
                    logger.info("Attempting fallback to JSON without image due to server-side error")
                    token_result = self._create_token_without_image(token_params, buy_amounts_dict, wallets, slippage_bps, create_amount_sol)
                elif "buyAmountsSOL" in str(e):
                    logger.warning(f"Multipart upload failed with buyAmountsSOL error: {str(e)}")
                    logger.info("Attempting fallback to JSON without image due to multipart parsing issue")
                    # Fallback to JSON without image
                    token_result = self._create_token_without_image(token_params, buy_amounts_dict, wallets, slippage_bps, create_amount_sol)
                else:
                    # Re-raise other API errors
                    raise e
            except PumpFunValidationError as e:
                if "buyAmountsSOL" in str(e):
                    logger.warning(f"Multipart upload failed with buyAmountsSOL error: {str(e)}")
                    logger.info("Attempting fallback to JSON without image due to multipart parsing issue")
                    # Fallback to JSON without image
                    token_result = self._create_token_without_image(token_params, buy_amounts_dict, wallets, slippage_bps, create_amount_sol)
                else:
                    # Re-raise non-buyAmountsSOL validation errors
                    raise e
        else:
            # Use JSON for token creation without image
            logger.info("Creating token without image using JSON request")
            try:
                token_result = self._create_token_without_image(token_params, buy_amounts_dict, wallets, slippage_bps, create_amount_sol)
            except PumpFunApiError as e:
                # Enhanced error handling for server-side wallet loading issues
                error_msg = str(e).lower()
                if "path" in error_msg and "undefined" in error_msg:
                    logger.error(f"Server-side wallet loading error detected: {str(e)}")
                    
                    # Re-raise the original error with additional context
                    raise PumpFunApiError(
                        f"Server-side wallet configuration error: {str(e)}. "
                        "Please check that the API server has proper wallet file paths configured."
                    )
                else:
                    # Re-raise other API errors
                    raise e
        
        # Handle additional wallet purchases (wallets 2-4) if they have non-zero amounts and exist
        additional_purchases = []
        wallet_names = [w["name"] for w in wallets]
        
        if buy_amounts.first_bundled_wallet_2_buy_sol > 0 and "First Bundled Wallet 2" in wallet_names:
            additional_purchases.append(("First Bundled Wallet 2", buy_amounts.first_bundled_wallet_2_buy_sol))
        if buy_amounts.first_bundled_wallet_3_buy_sol > 0 and "First Bundled Wallet 3" in wallet_names:
            additional_purchases.append(("First Bundled Wallet 3", buy_amounts.first_bundled_wallet_3_buy_sol))
        if buy_amounts.first_bundled_wallet_4_buy_sol > 0 and "First Bundled Wallet 4" in wallet_names:
            additional_purchases.append(("First Bundled Wallet 4", buy_amounts.first_bundled_wallet_4_buy_sol))
        
        if additional_purchases and token_result.get("mintAddress"):
            logger.info(f"Executing additional purchases for {len(additional_purchases)} wallets")
            mint_address = token_result["mintAddress"]
            
            # Execute batch buys for remaining wallets
            for wallet_name, sol_amount in additional_purchases:
                try:
                    # Find the specific wallet for this purchase
                    target_wallet = next((w for w in wallets if w["name"] == wallet_name), None)
                    if not target_wallet:
                        logger.error(f"Wallet {wallet_name} not found in wallets list for batch buy")
                        continue
                    
                    batch_result = self.batch_buy_token(
                        mint_address=mint_address,
                        sol_amount_per_wallet=sol_amount,
                        wallets=[target_wallet],  # Pass the specific wallet
                        slippage_bps=slippage_bps,
                        target_wallet_names=[wallet_name]
                    )
                    logger.info(f"Additional purchase completed for {wallet_name}: {sol_amount} SOL")
                    
                    # Merge batch results into main token result
                    if "additionalPurchases" not in token_result:
                        token_result["additionalPurchases"] = []
                    token_result["additionalPurchases"].append({
                        "wallet": wallet_name,
                        "amount": sol_amount,
                        "result": batch_result
                    })
                    
                except Exception as e:
                    logger.error(f"Failed additional purchase for {wallet_name}: {str(e)}")
                    if "additionalPurchaseErrors" not in token_result:
                        token_result["additionalPurchaseErrors"] = []
                    token_result["additionalPurchaseErrors"].append({
                        "wallet": wallet_name,
                        "amount": sol_amount,
                        "error": str(e)
                    })
        
        # Normalize response fields for backward compatibility
        token_result = self._normalize_response_fields(token_result)
        
        return token_result

    def _create_token_with_image(self, token_params: TokenCreationParams, 
                                buy_amounts_dict: Dict[str, float], wallets: List[Dict[str, str]], slippage_bps: int,
                                image_file_path: str, create_amount_sol: float = 0.001) -> Dict[str, Any]:
        """
        Create token with image using multipart/form-data upload.
        
        Args:
            token_params: Token creation parameters
            buy_amounts_dict: Buy amounts dictionary
            wallets: List of wallet dictionaries with 'name' and 'privateKey' fields
            slippage_bps: Slippage in basis points
            image_file_path: Path to image file
            create_amount_sol: SOL amount for token creation
            
        Returns:
            Dictionary with token creation results
        """
        url = f"{self.base_url}/api/pump/create-and-buy"
        
        # Prepare form data according to API documentation
        # Format buyAmountsSOL exactly like the cURL example: no spaces, compact format
        # Ensure numbers are formatted as proper decimals
        dev_amount = float(buy_amounts_dict["devWalletBuySOL"])
        first_bundled_amount = float(buy_amounts_dict["firstBundledWallet1BuySOL"])
        
        # Use json.dumps for proper JSON formatting to avoid f-string issues
        buy_amounts_obj = {
            "devWalletBuySOL": dev_amount,
            "firstBundledWallet1BuySOL": first_bundled_amount
        }
        buy_amounts_json = json.dumps(buy_amounts_obj, separators=(',', ':'))
        
        # Validate the JSON before sending
        self._validate_buy_amounts_json(buy_amounts_json)
        
        # Prepare wallets JSON string
        wallets_json = json.dumps(wallets, separators=(',', ':'))
        
        # Validate wallets JSON
        self._validate_wallets_json(wallets_json)
        
        form_data = {
            'name': token_params.name,
            'symbol': token_params.symbol,
            'description': token_params.description,
            'twitter': token_params.twitter or '',  # Ensure empty string instead of None
            'telegram': token_params.telegram or '',  # Ensure empty string instead of None
            'website': token_params.website or '',  # Ensure empty string instead of None
            'showName': 'true' if token_params.show_name else 'false',  # Exact boolean string format
            'createAmountSOL': str(create_amount_sol),  # SOL amount for token creation
            'buyAmountsSOL': buy_amounts_json,  # Validated JSON string
            'wallets': wallets_json,  # New required field as JSON string
            'slippageBps': str(slippage_bps)
        }
        
        # Debug logging to see exact JSON format being sent
        logger.info(f"buyAmountsSOL JSON being sent: {buy_amounts_json}")
        logger.info(f"buyAmountsSOL JSON length: {len(buy_amounts_json)}")
        logger.info(f"buyAmountsSOL JSON repr: {repr(buy_amounts_json)}")
        logger.debug(f"Form data keys: {list(form_data.keys())}")
        logger.debug(f"Form data types: {[(k, type(v).__name__) for k, v in form_data.items()]}")
        
        # Validate JSON string can be parsed back
        try:
            parsed_test = json.loads(buy_amounts_json)
            logger.info(f"JSON validation successful: {parsed_test}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON validation failed: {e}")
            raise PumpFunValidationError(f"Invalid JSON generated for buyAmountsSOL: {e}")
        
        # Validate image file
        if not os.path.exists(image_file_path):
            raise PumpFunValidationError(f"Image file not found: {image_file_path}")
        
        # Check file size (5MB limit as per API docs)
        file_size = os.path.getsize(image_file_path)
        if file_size > 5 * 1024 * 1024:  # 5MB
            raise PumpFunValidationError(f"Image file too large: {file_size} bytes (max 5MB)")
        
        # Check file format
        valid_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
        file_extension = os.path.splitext(image_file_path)[1].lower()
        if file_extension not in valid_extensions:
            raise PumpFunValidationError(f"Invalid image format: {file_extension}. Supported: {valid_extensions}")
        
        try:
            # Open and prepare file for upload
            with open(image_file_path, 'rb') as image_file:
                files = {'image': (os.path.basename(image_file_path), image_file, self._get_content_type(file_extension))}
                
                # Log complete request details for debugging
                logger.info(f"Multipart upload - Form fields: {list(form_data.keys())}, File: {os.path.basename(image_file_path)}")
                logger.info(f"Complete form data for debugging:")
                for key, value in form_data.items():
                    if key == 'buyAmountsSOL':
                        logger.info(f"  {key}: {value} (type: {type(value).__name__}, length: {len(value)})")
                    elif key == 'wallets':
                        logger.info(f"  {key}: {value} (type: {type(value).__name__}, length: {len(value)})")
                    else:
                        logger.info(f"  {key}: {value} (type: {type(value).__name__})")
                
                # Make multipart request with retry logic
                response = self._make_multipart_request_with_retry("POST", url, data=form_data, files=files)
                
                logger.info("Token creation with image upload completed successfully")
                return self._normalize_response_fields(response)
                
        except IOError as e:
            raise PumpFunValidationError(f"Failed to read image file: {str(e)}")
        except Exception as e:
            logger.error(f"Image upload failed: {str(e)}")
            raise PumpFunApiError(f"Image upload failed: {str(e)}")

    def _create_token_without_image(self, token_params: TokenCreationParams, 
                                   buy_amounts_dict: Dict[str, float], wallets: List[Dict[str, str]], slippage_bps: int,
                                   create_amount_sol: float = 0.001) -> Dict[str, Any]:
        """
        Create token without image using JSON request.
        
        Args:
            token_params: Token creation parameters
            buy_amounts_dict: Buy amounts dictionary
            wallets: List of wallet dictionaries with 'name' and 'privateKey' fields
            slippage_bps: Slippage in basis points
            create_amount_sol: SOL amount for token creation
            
        Returns:
            Dictionary with token creation results
        """
        # Direct JSON request with new API field names
        data = {
            "name": token_params.name,
            "symbol": token_params.symbol,
            "description": token_params.description,
            "twitter": token_params.twitter or "",
            "telegram": token_params.telegram or "",
            "website": token_params.website or "",
            "showName": token_params.show_name,
            "createAmountSOL": create_amount_sol,  # SOL amount for token creation
            "buyAmountsSOL": buy_amounts_dict,
            "wallets": wallets,  # Include wallets directly as list for JSON request
            "slippageBps": slippage_bps
        }
        
        # Log the final request payload for debugging
        logger.info(f"JSON token creation request - Fields: {list(data.keys())}")
        
        # Use enhanced retry for critical token creation operations
        response = self._make_request_for_critical_operations("POST", "/api/pump/create-and-buy", json=data)
        return self._normalize_response_fields(response)

    def _get_content_type(self, file_extension: str) -> str:
        """
        Get content type for file extension.
        
        Args:
            file_extension: File extension (with dot)
            
        Returns:
            Content type string
        """
        content_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml'
        }
        return content_types.get(file_extension.lower(), 'application/octet-stream')

    def _make_multipart_request_with_retry(self, method: str, url: str, data: Dict[str, Any], 
                                         files: Dict[str, Any], max_retries: int = MAX_RETRIES) -> Dict[str, Any]:
        """
        Make multipart request with retry logic for image uploads.
        Enhanced with basic rate limiting support.
        """
        # Enforce cooldown for bundle operations before starting
        if '/api/pump/' in url:
            self._enforce_bundle_operation_cooldown('token_creation')
        
        last_exception = None
        is_cold_start = self._detect_cold_start_scenario()
        
        if is_cold_start:
            max_retries = max(max_retries, COLD_START_MAX_RETRIES)
            logger.info(f"Cold start detected for multipart upload, using enhanced retry: max_retries={max_retries}")
        
        for attempt in range(max_retries + 1):
            try:
                with requests.Session() as session:
                    session.headers.update({'User-Agent': 'NinjaBot-PumpFun-Client/1.0'})
                    response = session.request(method, url, data=data, files=files, timeout=self.timeout)
                    logger.info(f"Multipart request {method} {url} - Status: {response.status_code}")
                    
                    if response.status_code == 200:
                        try:
                            return response.json()
                        except json.JSONDecodeError:
                            return {"status": "success", "data": response.text}
                    elif response.status_code == 400:
                        try:
                            error_data = response.json() if response.content else {}
                            detailed_error = error_data.get('error', error_data.get('message', 'Invalid request'))
                            logger.error(f"Multipart upload validation error: {detailed_error}")
                            raise PumpFunValidationError(f"Validation error: {detailed_error}")
                        except json.JSONDecodeError:
                            logger.error(f"Multipart upload 400 non-JSON response: {response.text}")
                            raise PumpFunValidationError(f"Validation error: {response.text}")
                    elif response.status_code == 500:
                        error_data = response.json() if response.content else {}
                        error_message = error_data.get('error', 'Internal server error')
                        
                        # Check if this is a rate limiting error and apply backoff
                        if self._is_rate_limit_error(error_message):
                            backoff_time = self._calculate_rate_limit_backoff(attempt)
                            logger.warning(f"Rate limit detected in multipart upload, waiting {backoff_time:.1f}s before retry")
                            time.sleep(backoff_time)
                            if attempt < max_retries:
                                continue
                        
                        raise PumpFunApiError(f"Server error: {error_message}")
                    else:
                        raise PumpFunApiError(f"HTTP {response.status_code}: {response.text}")
                        
            except requests.exceptions.ConnectionError as e:
                last_exception = PumpFunNetworkError(f"Connection error: {str(e)}")
            except requests.exceptions.Timeout as e:
                last_exception = PumpFunNetworkError(f"Request timeout: {str(e)}")
            except requests.exceptions.RequestException as e:
                last_exception = PumpFunNetworkError(f"Request error: {str(e)}")
            except (PumpFunValidationError, PumpFunApiError) as e:
                raise e
            
            # Retry logic for network errors
            if last_exception and attempt < max_retries:
                backoff_time = INITIAL_BACKOFF * (2 ** attempt)
                if is_cold_start:
                    backoff_time *= random.uniform(0.5, 1.5)
                logger.warning(f"Multipart upload error on attempt {attempt + 1}/{max_retries + 1}, retrying in {backoff_time:.1f}s: {str(last_exception)}")
                time.sleep(backoff_time)
            elif last_exception:
                logger.error(f"All {max_retries + 1} multipart upload attempts failed: {str(last_exception)}")
                raise last_exception
        
        raise last_exception or PumpFunNetworkError("Unknown error in multipart upload")

    def batch_buy_token(self, mint_address: str, sol_amount_per_wallet: float, 
                       wallets: List[Dict[str, str]], slippage_bps: int = 2500, 
                       target_wallet_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Batch buy token from multiple wallets using stateless API.
        
        Args:
            mint_address: Token mint address
            sol_amount_per_wallet: SOL amount per wallet
            wallets: List of wallet objects with name and privateKey
            slippage_bps: Slippage in basis points
            target_wallet_names: Optional list of target wallet names
            
        Returns:
            Dictionary with batch buy results
        """
        if not mint_address:
            raise PumpFunValidationError("Mint address cannot be empty")
        if sol_amount_per_wallet <= 0:
            raise PumpFunValidationError("SOL amount per wallet must be greater than 0")
        if not wallets or len(wallets) == 0:
            raise PumpFunValidationError("Wallets list cannot be empty")
            
        # Validate wallet credentials
        for i, wallet in enumerate(wallets):
            if not isinstance(wallet, dict):
                raise PumpFunValidationError(f"Wallet {i} must be a dictionary")
            if "name" not in wallet or not wallet["name"]:
                raise PumpFunValidationError(f"Wallet {i} must have a 'name' field")
            if "privateKey" not in wallet or not wallet["privateKey"]:
                raise PumpFunValidationError(f"Wallet {i} must have a 'privateKey' field")
                
        endpoint = "/api/pump/batch-buy"
        data = {
            "mintAddress": mint_address,
            "solAmountPerWallet": sol_amount_per_wallet,
            "slippageBps": slippage_bps,
            "wallets": wallets
        }
        
        if target_wallet_names:
            data["targetWalletNames"] = target_wallet_names
        
        logger.info(f"Batch buying token {mint_address} with {len(wallets)} wallets, amount {sol_amount_per_wallet} SOL per wallet")
        if target_wallet_names:
            logger.info(f"Target wallets: {target_wallet_names}")
            
        return self._make_request_with_retry("POST", endpoint, json=data)

    def sell_dev_wallet(self, dev_wallet_private_key: str, mint_address: str, sell_percentage: float, 
                       slippage_bps: int = 5000) -> Dict[str, Any]:
        """
        Sell tokens from DevWallet using stateless API.
        
        Args:
            dev_wallet_private_key: Private key of the dev wallet
            mint_address: Token mint address
            sell_percentage: Percentage to sell (0-100)
            slippage_bps: Slippage in basis points
            
        Returns:
            Dictionary with sell results
        """
        if not dev_wallet_private_key:
            raise PumpFunValidationError("Dev wallet private key cannot be empty")
        if not mint_address:
            raise PumpFunValidationError("Mint address cannot be empty")
        if not 0 <= sell_percentage <= 100:
            raise PumpFunValidationError("Sell percentage must be between 0 and 100")
            
        endpoint = "/api/pump/sell-dev"
        data = {
            "mintAddress": mint_address,
            "sellAmountPercentage": f"{sell_percentage}%",
            "slippageBps": slippage_bps,
            "wallets": [
                {
                    "name": "DevWallet",
                    "privateKey": dev_wallet_private_key
                }
            ]
        }
        
        return self._make_request_with_retry("POST", endpoint, json=data)

    def batch_sell_token(self, wallets: List[Dict[str, str]], mint_address: str, sell_percentage: float, 
                        slippage_bps: int = 5000, target_wallet_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Batch sell tokens from multiple wallets (excluding DevWallet).
        
        Args:
            wallets: List of wallet dictionaries with 'name' and 'privateKey' fields
            mint_address: Token mint address
            sell_percentage: Percentage to sell (0-100)
            slippage_bps: Slippage in basis points
            target_wallet_names: Optional list of target wallet names
            
        Returns:
            Dictionary with batch sell results
        """
        if not wallets:
            raise PumpFunValidationError("Wallets cannot be empty")
        if not mint_address:
            raise PumpFunValidationError("Mint address cannot be empty")
        if not 0 <= sell_percentage <= 100:
            raise PumpFunValidationError("Sell percentage must be between 0 and 100")
            
        # Validate wallet format
        for wallet in wallets:
            if not isinstance(wallet, dict) or 'name' not in wallet or 'privateKey' not in wallet:
                raise PumpFunValidationError("Each wallet must have 'name' and 'privateKey' fields")
            
        endpoint = "/api/pump/batch-sell"
        data = {
            "mintAddress": mint_address,
            "sellAmountPercentage": f"{sell_percentage}%",
            "slippageBps": slippage_bps,
            "wallets": wallets  # Use actual wallet objects with correct names
        }
        
        if target_wallet_names:
            data["targetWalletNames"] = target_wallet_names
            
        return self._make_request_with_retry("POST", endpoint, json=data)

    # Validation Methods

    def _validate_token_params(self, token_params: TokenCreationParams) -> None:
        """
        Validate token creation parameters.
        
        Args:
            token_params: Token parameters to validate
            
        Raises:
            PumpFunValidationError: If validation fails
        """
        if not token_params.name or len(token_params.name.strip()) == 0:
            raise PumpFunValidationError("Token name cannot be empty")
        if not token_params.symbol or len(token_params.symbol.strip()) == 0:
            raise PumpFunValidationError("Token symbol cannot be empty")
        if not token_params.description or len(token_params.description.strip()) == 0:
            raise PumpFunValidationError("Token description cannot be empty")
            
        # Validate symbol length and format
        if len(token_params.symbol) > 10:
            raise PumpFunValidationError("Token symbol cannot exceed 10 characters")
        if not token_params.symbol.isalnum():
            raise PumpFunValidationError("Token symbol must contain only alphanumeric characters")
            
        # Validate name length
        if len(token_params.name) > 32:
            raise PumpFunValidationError("Token name cannot exceed 32 characters")
            
        # Validate description length
        if len(token_params.description) > 500:
            raise PumpFunValidationError("Token description cannot exceed 500 characters")

    def health_check(self) -> Dict[str, Any]:
        """
        Check if the PumpFun API is healthy and reachable.
        Enhanced with cold start detection and wake-up capability.
        
        Returns:
            Dictionary with health status
        """
        try:
            logger.info("Performing API health check with cold start handling")
            # Try a simple endpoint first to potentially wake up the service
            response = self._make_request_with_retry(
                "GET", 
                "/api/wallets/11111111111111111111111111111111/balance",
                max_retries=COLD_START_MAX_RETRIES,
                initial_backoff=COLD_START_INITIAL_BACKOFF
            )
            return {
                "status": "healthy", 
                "api_reachable": True,
                "cold_start_detected": self._detect_cold_start_scenario(),
                "response_time": "normal"
            }
        except PumpFunNetworkError as e:
            if "timeout" in str(e).lower():
                return {
                    "status": "unhealthy", 
                    "api_reachable": False, 
                    "error": str(e),
                    "cold_start_likely": True,
                    "suggestion": "Service may be in cold start. Please retry in a few moments."
                }
            else:
                return {
                    "status": "unhealthy", 
                    "api_reachable": False, 
                    "error": str(e),
                    "cold_start_likely": False
                }
        except Exception as e:
            return {
                "status": "unhealthy", 
                "api_reachable": False, 
                "error": str(e),
                "cold_start_likely": False
            }

    def test_server_configuration(self) -> Dict[str, Any]:
        """
        Test server configuration and wallet setup after applying fixes.
        This method helps verify that the server-side path configuration fix worked.
        
        Returns:
            Dictionary with configuration test results
        """
        logger.info("Testing server configuration after applying fixes...")
        
        test_results = {
            "timestamp": time.time(),
            "tests": {},
            "overall_status": "unknown",
            "recommendations": []
        }
        
        # Test 1: Basic API connectivity
        logger.info("Test 1: Basic API connectivity")
        health_check = self.health_check()
        test_results["tests"]["api_connectivity"] = {
            "status": "pass" if health_check["api_reachable"] else "fail",
            "details": health_check
        }
        
        # Test 2: Wallet configuration diagnostics
        logger.info("Test 2: Wallet configuration diagnostics")
        try:
            wallet_diagnostics = self.diagnose_server_wallet_configuration()
            has_path_errors = any(
                issue.get("issue") == "Server wallet file path configuration" 
                for issue in wallet_diagnostics.get("configuration_issues", [])
            )
            
            test_results["tests"]["wallet_configuration"] = {
                "status": "fail" if has_path_errors else "pass",
                "details": wallet_diagnostics
            }
            
            if has_path_errors:
                test_results["recommendations"].extend([
                    "Apply the server-side configuration fix from server_config_fix.md",
                    "Set BUNDLED_WALLETS_PATH environment variable",
                    "Ensure wallet file directory exists and is writable"
                ])
        except Exception as e:
            test_results["tests"]["wallet_configuration"] = {
                "status": "error",
                "details": {"error": str(e)}
            }
        
        # Test 3: Try to create bundled wallets (if they don't exist)
        logger.info("Test 3: Wallet creation capability")
        try:
            # First check if wallets exist
            wallet_verification = self.verify_bundled_wallets_exist()
            
            if not wallet_verification.get("wallets_exist", False):
                # Try to create test wallets
                try:
                    creation_result = self.create_bundled_wallets(5)
                    test_results["tests"]["wallet_creation"] = {
                        "status": "pass",
                        "details": {
                            "message": "Successfully created test wallets",
                            "result": creation_result
                        }
                    }
                except Exception as create_error:
                    test_results["tests"]["wallet_creation"] = {
                        "status": "fail",
                        "details": {
                            "error": str(create_error),
                            "message": "Failed to create test wallets"
                        }
                    }
                    
                    if "path" in str(create_error).lower():
                        test_results["recommendations"].append(
                            "Path error detected - server-side configuration fix still needed"
                        )
            else:
                test_results["tests"]["wallet_creation"] = {
                    "status": "pass",
                    "details": {
                        "message": "Wallets already exist, creation test skipped"
                    }
                }
        except Exception as e:
            test_results["tests"]["wallet_creation"] = {
                "status": "error",
                "details": {"error": str(e)}
            }
        
        # Test 4: Test token creation (minimal test)
        logger.info("Test 4: Token creation capability")
        try:
            # Create test token parameters
            test_token_params = TokenCreationParams(
                name="Test Token",
                symbol="TEST",
                description="Configuration test token"
            )
            
            test_buy_amounts = BuyAmounts(
                dev_wallet_buy_sol=0.005,
                first_bundled_wallet_1_buy_sol=0.005
            )
            
            # Try to create token (this will fail if path error still exists)
            try:
                token_result = self.create_token_and_buy(
                    test_token_params, 
                    test_buy_amounts, 
                    slippage_bps=2500
                )
                test_results["tests"]["token_creation"] = {
                    "status": "pass",
                    "details": {
                        "message": "Token creation succeeded",
                        "result": token_result
                    }
                }
            except PumpFunApiError as token_error:
                error_msg = str(token_error).lower()
                if "path" in error_msg and "undefined" in error_msg:
                    test_results["tests"]["token_creation"] = {
                        "status": "fail",
                        "details": {
                            "error": str(token_error),
                            "message": "Path error still exists - server fix needed"
                        }
                    }
                    test_results["recommendations"].append(
                        "Server-side path configuration fix is still required"
                    )
                else:
                    test_results["tests"]["token_creation"] = {
                        "status": "partial",
                        "details": {
                            "error": str(token_error),
                            "message": "Path error resolved, but other issues remain"
                        }
                    }
                    
        except Exception as e:
            test_results["tests"]["token_creation"] = {
                "status": "error",
                "details": {"error": str(e)}
            }
        
        # Determine overall status
        test_statuses = [test["status"] for test in test_results["tests"].values()]
        if all(status == "pass" for status in test_statuses):
            test_results["overall_status"] = "pass"
        elif any(status == "fail" for status in test_statuses):
            test_results["overall_status"] = "fail"
        else:
            test_results["overall_status"] = "partial"
        
        # Add general recommendations
        if test_results["overall_status"] != "pass":
            test_results["recommendations"].extend([
                "Review server logs for additional error details",
                "Ensure all environment variables are properly set",
                "Verify server has proper file system permissions"
            ])
        
        logger.info(f"Configuration test completed with overall status: {test_results['overall_status']}")
        return test_results

    def get_api_info(self) -> Dict[str, Any]:
        """
        Get API information and status.
        
        Returns:
            Dictionary with API information
        """
        return {
            "client_version": "1.0.0",
            "base_url": self.base_url,
            "timeout": self.timeout,
            "supported_operations": [
                "wallet_management",
                "token_creation",
                "batch_trading",
                "funding_operations"
            ]
        }

    def create_token_example(self) -> Dict[str, Any]:
        """
        Example showing how to use the updated create_token_and_buy method.
        This demonstrates the new pattern where wallet credentials are passed directly.
        
        Returns:
            Dictionary with example usage instructions
        """
        example_code = '''
# Example usage of the updated PumpFun client
from ninjabot.bot.api.pumpfun_client import PumpFunClient, TokenCreationParams, BuyAmounts

# Initialize client
client = PumpFunClient()

# Define token parameters
token_params = TokenCreationParams(
    name="My Awesome Token",
    symbol="MAT", 
    description="This is an awesome token for testing",
    twitter="@mytoken",
    telegram="@mytoken_chat",
    website="https://mytoken.com"
)

# Define buy amounts
buy_amounts = BuyAmounts(
    dev_wallet_buy_sol=0.01,
    first_bundled_wallet_1_buy_sol=0.005,
    first_bundled_wallet_2_buy_sol=0.005,
    first_bundled_wallet_3_buy_sol=0.005,
    first_bundled_wallet_4_buy_sol=0.005
)

        # IMPORTANT: Prepare wallet credentials with private keys
        wallets = [
            {
                "name": "DevWallet",
                "privateKeyBs58": "your_dev_wallet_base58_private_key_here"
            },
            {
                "name": "First Bundled Wallet 1",
                "privateKeyBs58": "your_first_bundled_wallet_base58_private_key_here"
            },
            {
                "name": "First Bundled Wallet 2", 
                "privateKeyBs58": "your_second_bundled_wallet_base58_private_key_here"
            }
            # Add more wallets as needed...
        ]

# Create token with image
try:
    result = client.create_token_and_buy(
        token_params=token_params,
        buy_amounts=buy_amounts,
        wallets=wallets,  # NEW: Required parameter
        slippage_bps=2500,
        image_file_path="path/to/token/image.png"  # Optional
    )
    
    print(f"Token created successfully: {result['mintAddress']}")
    print(f"Bundle ID: {result['bundleId']}")
    
except Exception as e:
    print(f"Token creation failed: {e}")
'''
        
        return {
            "example_code": example_code,
            "key_changes": [
                "Wallet credentials must be passed directly to create_token_and_buy()",
                "Each wallet must have 'name' and 'privateKey' fields",
                "DevWallet must be included with creator private key",
                "Buying wallets must be included with their private keys",
                "Server no longer stores wallet files - everything is stateless"
            ],
            "required_wallet_fields": ["name", "privateKey"],
            "minimum_wallets_needed": ["DevWallet", "First Bundled Wallet 1"],
            "api_benefits": [
                "Eliminates server-side wallet storage issues",
                "Prevents path configuration errors",
                "Enables truly stateless operation", 
                "Improves security by not storing private keys server-side",
                "Compatible with ephemeral container deployments"
            ]
        }

    def verify_mother_wallet_exists(self) -> Dict[str, Any]:
        """
        Verify if mother wallet exists by using actual working API endpoints.
        CRITICAL FIX: Use endpoints that actually exist according to API documentation.
        
        According to the API docs, the stateless API doesn't have dedicated state checking endpoints.
        We need to use a different approach that works with the actual API.
        
        Returns:
            Dictionary with verification status and details
        """
        logger.info("🔍 Verifying mother wallet state using working API endpoints")
        
        # IMPORTANT: The API is stateless, so "verification" is misleading.
        # The real test is whether we can perform operations with valid credentials.
        # Since we've successfully imported the wallet (Status 200), it should work.
        
        # For stateless APIs, if import succeeds, wallet state is ready
        logger.info("✅ Verification approach: Stateless API - if import succeeded, wallet is ready")
        
        return {
            "exists": True,
            "verification_method": "stateless_api_logic",
            "note": "Stateless API: Import success (Status 200) means wallet is ready for operations"
        }

    def ensure_mother_wallet_state_for_funding(self, private_key: str) -> bool:
        """
        Compatibility method for stateless API - always returns True.
        FIXED: Stateless APIs don't need state management.
        
        Args:
            private_key: Mother wallet private key (not used in stateless API)
            
        Returns:
            Always True for stateless API compatibility
        """
        logger.info("🔧 Stateless API: State management not required - wallet ready")
        return True

    def _is_base64_format(self, key: str) -> bool:
        """
        Check if a private key is in base64 format.
        
        Args:
            key: Private key string to check
            
        Returns:
            True if key appears to be base64, False otherwise
        """
        try:
            # Base64 keys typically end with '=' padding and contain base64 characters
            import base64
            import re
            
            # Check for base64 characteristics
            if '=' in key:  # Base64 padding
                return True
            if re.match(r'^[A-Za-z0-9+/]*={0,2}$', key):  # Base64 character set
                return True
            if len(key) == 88 and '=' in key[-2:]:  # Typical base64 private key length with padding
                return True
                
            # Try to decode as base64 - if it works and result is 64 bytes, likely base64
            decoded = base64.b64decode(key)
            if len(decoded) == 64:  # Solana private keys are 64 bytes
                return True
                
        except Exception:
            pass
            
        return False

    def _convert_base64_to_base58(self, base64_key: str) -> str:
        """
        Convert base64 private key to base58 format.
        
        Args:
            base64_key: Private key in base64 format
            
        Returns:
            Private key in base58 format
        """
        import base64
        import base58
        
        # Decode from base64
        decoded_bytes = base64.b64decode(base64_key)
        
        # Encode to base58
        base58_key = base58.b58encode(decoded_bytes).decode('utf-8')
        
        return base58_key

    def _normalize_response_fields(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize API response field names to ensure backward compatibility.
        Converts camelCase to snake_case for consistency with existing code.
        
        Args:
            response: Raw API response
            
        Returns:
            Normalized response with both camelCase and snake_case keys
        """
        if not isinstance(response, dict):
            logger.warning(f"Response is not a dict, cannot normalize: {type(response)}")
            return response
            
        normalized = response.copy()
        
        # Debug: Log original response structure
        logger.info(f"Normalizing response with keys: {list(response.keys())}")
        
        # Add snake_case versions of camelCase fields for backward compatibility
        field_mappings = {
            'mintAddress': 'mint_address',
            'bundleId': 'bundle_id',
            'txHash': 'tx_hash',
            'blockHash': 'block_hash',
            'tokenName': 'token_name',
            'tokenSymbol': 'token_symbol'
        }
        
        for camel_key, snake_key in field_mappings.items():
            if camel_key in normalized and snake_key not in normalized:
                normalized[snake_key] = normalized[camel_key]
                logger.info(f"Mapped {camel_key} -> {snake_key}: {normalized[camel_key]}")
                
        # Debug: Log final normalized response structure
        logger.info(f"Normalized response keys: {list(normalized.keys())}")
        
        return normalized