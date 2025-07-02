#!/usr/bin/env python3
"""
PumpFun API Client for Solana wallet management and Pump.fun platform interactions.
Handles token creation, batch buying, and batch selling using Jito bundles.
"""

import json
import time
import logging
import requests
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


class PumpFunApiError(Exception):
    """Base exception for PumpFun API errors"""
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
    first_bundled_wallet_2_buy_sol: float = 0.01
    first_bundled_wallet_3_buy_sol: float = 0.01
    first_bundled_wallet_4_buy_sol: float = 0.01


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
                # Enhanced error handling for validation errors
                try:
                    error_data = response.json() if response.content else {}
                    detailed_error = error_data.get('error', 'Invalid request')
                    # Log the full error response for debugging
                    logger.error(f"PumpFun API 400 error details: {error_data}")
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

    def _make_request_for_critical_operations(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make request with maximum retry effort for critical operations like wallet creation.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            **kwargs: Additional request parameters
            
        Returns:
            API response as dictionary
        """
        return self._make_request_with_retry(
            method, 
            endpoint, 
            max_retries=COLD_START_MAX_RETRIES,
            initial_backoff=COLD_START_INITIAL_BACKOFF,
            **kwargs
        )

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
            
            # Handle direct response format (no success wrapper)
            elif "address" in response or "publicKey" in response or "public_key" in response:
                normalized_response = {}
                
                if "address" in response:
                    normalized_response["address"] = response["address"]
                elif "publicKey" in response:
                    normalized_response["address"] = response["publicKey"]
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
        Import bundled (child) wallets.
        
        Args:
            wallets: List of wallet dictionaries with 'name' and 'privateKey' fields
            
        Returns:
            Dictionary with imported wallet details
        """
        if not wallets:
            raise PumpFunValidationError("Wallets list cannot be empty")
            
        # Validate wallet format
        for wallet in wallets:
            if 'name' not in wallet or 'privateKey' not in wallet:
                raise PumpFunValidationError("Each wallet must have 'name' and 'privateKey' fields")
                
        endpoint = "/api/wallets/bundled/import"
        data = {"wallets": wallets}
        
        return self._make_request_with_retry("POST", endpoint, json=data)

    def fund_bundled_wallets(self, amount_per_wallet: float) -> Dict[str, Any]:
        """
        Fund bundled wallets from the airdrop wallet.
        
        Args:
            amount_per_wallet: SOL amount to send to each wallet
            
        Returns:
            Dictionary with funding transaction results
        """
        if amount_per_wallet <= 0:
            raise PumpFunValidationError("Amount per wallet must be greater than 0")
        
        # Validate reasonable amount (between 0.001 and 10 SOL)
        if amount_per_wallet < 0.001:
            raise PumpFunValidationError("Amount per wallet too small (minimum 0.001 SOL)")
        if amount_per_wallet > 10:
            raise PumpFunValidationError("Amount per wallet too large (maximum 10 SOL)")
            
        endpoint = "/api/wallets/fund-bundled"
        
        # Use the correct parameter name from API documentation
        data = {"amountPerWalletSOL": amount_per_wallet}
        
        logger.info(f"Funding bundled wallets with {amount_per_wallet} SOL per wallet using correct API format")
        
        return self._make_request_with_retry("POST", endpoint, json=data)

    def verify_bundled_wallets_exist(self) -> Dict[str, Any]:
        """
        Verify if bundled wallets exist on the API server.
        
        Returns:
            Dictionary with verification results including wallet count and details
        """
        try:
            # Try to get a simple balance check on the first bundled wallet
            # This is an indirect way to verify if wallets are imported
            # Since there's no explicit "list bundled wallets" endpoint documented
            
            # Alternative: Try to fund with 0 amount to test if wallets exist
            test_endpoint = "/api/wallets/fund-bundled"
            test_data = {"amountPerWalletSOL": 0.0}
            
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

    def return_funds_to_mother(self, leave_dust: bool = False) -> Dict[str, Any]:
        """
        Return funds from bundled wallets to the airdrop wallet.
        
        Args:
            leave_dust: Whether to leave small amounts in wallets
            
        Returns:
            Dictionary with return transaction results
        """
        endpoint = "/api/wallets/return-funds"
        data = {"leaveDust": leave_dust}
        
        return self._make_request_with_retry("POST", endpoint, json=data)

    def get_wallet_balance(self, public_key: str) -> Dict[str, Any]:
        """
        Get wallet SOL balance (updated to use enhanced balance endpoint with fallback).
        
        Args:
            public_key: Wallet public key
            
        Returns:
            Dictionary with SOL balance information
        """
        if not public_key:
            raise PumpFunValidationError("Public key cannot be empty")
            
        # First try the enhanced endpoint
        endpoint = f"/api/wallets/{public_key}/balance/sol"
        
        try:
            response = self._make_request_with_retry("GET", endpoint)
            
            # Extract SOL balance from new response format
            if "data" in response and "sol" in response["data"]:
                sol_data = response["data"]["sol"]
                # Return in backward-compatible format
                return {
                    "message": response.get("message", "Balance retrieved successfully."),
                    "data": {
                        "publicKey": response["data"]["publicKey"],
                        "balance": sol_data["balance"],
                        "lamports": sol_data["lamports"]
                    }
                }
            else:
                # Fallback for unexpected response format
                return response
                
        except PumpFunApiError as e:
            # If 404 or similar error, fall back to legacy endpoint
            if "404" in str(e) or "Cannot GET" in str(e):
                logger.warning(f"Enhanced balance endpoint not available, falling back to legacy endpoint: {str(e)}")
                return self._get_wallet_balance_legacy(public_key)
            else:
                # Re-raise other API errors
                raise e

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
            logger.error(f"Legacy balance endpoint also failed: {str(e)}")
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
        Get wallet SOL balance using enhanced endpoint with fallback.
        
        Args:
            public_key: Wallet public key
            
        Returns:
            Dictionary with detailed SOL balance information
        """
        if not public_key:
            raise PumpFunValidationError("Public key cannot be empty")
            
        endpoint = f"/api/wallets/{public_key}/balance/sol"
        
        try:
            return self._make_request_with_retry("GET", endpoint)
        except PumpFunApiError as e:
            # If 404 or similar error, fall back to legacy endpoint
            if "404" in str(e) or "Cannot GET" in str(e):
                logger.warning(f"Enhanced SOL balance endpoint not available, falling back to legacy: {str(e)}")
                return self._get_wallet_balance_legacy(public_key)
            else:
                # Re-raise other API errors
                raise e

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

    def create_token_and_buy(self, token_params: TokenCreationParams, 
                           buy_amounts: BuyAmounts, slippage_bps: int = 2500) -> Dict[str, Any]:
        """
        Create a token and perform initial buys.
        
        Args:
            token_params: Token creation parameters
            buy_amounts: Buy amounts for different wallets
            slippage_bps: Slippage in basis points
            
        Returns:
            Dictionary with token creation and buy results
        """
        # Validate token parameters
        self._validate_token_params(token_params)
        
        endpoint = "/api/pump/create-and-buy"
        
        # Prepare buy amounts dictionary
        buy_amounts_dict = {
            "devWalletBuySOL": buy_amounts.dev_wallet_buy_sol,
            "firstBundledWallet1BuySOL": buy_amounts.first_bundled_wallet_1_buy_sol,
            "firstBundledWallet2BuySOL": buy_amounts.first_bundled_wallet_2_buy_sol,
            "firstBundledWallet3BuySOL": buy_amounts.first_bundled_wallet_3_buy_sol,
            "firstBundledWallet4BuySOL": buy_amounts.first_bundled_wallet_4_buy_sol
        }
        
        data = {
            **asdict(token_params),
            "buyAmountsSOL": buy_amounts_dict,
            "slippageBps": slippage_bps
        }
        
        # Use enhanced retry for critical token creation operations
        logger.info("Creating token with enhanced retry logic for cold start handling")
        return self._make_request_for_critical_operations("POST", endpoint, json=data)

    def batch_buy_token(self, mint_address: str, sol_amount_per_wallet: float, 
                       slippage_bps: int = 2500, target_wallet_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Batch buy token from multiple wallets.
        
        Args:
            mint_address: Token mint address
            sol_amount_per_wallet: SOL amount per wallet
            slippage_bps: Slippage in basis points
            target_wallet_names: Optional list of target wallet names
            
        Returns:
            Dictionary with batch buy results
        """
        if not mint_address:
            raise PumpFunValidationError("Mint address cannot be empty")
        if sol_amount_per_wallet <= 0:
            raise PumpFunValidationError("SOL amount per wallet must be greater than 0")
            
        endpoint = "/api/pump/batch-buy"
        data = {
            "mintAddress": mint_address,
            "solAmountPerWallet": sol_amount_per_wallet,
            "slippageBps": slippage_bps
        }
        
        if target_wallet_names:
            data["targetWalletNames"] = target_wallet_names
            
        return self._make_request_with_retry("POST", endpoint, json=data)

    def sell_dev_wallet(self, mint_address: str, sell_percentage: float, 
                       slippage_bps: int = 2500) -> Dict[str, Any]:
        """
        Sell tokens from DevWallet.
        
        Args:
            mint_address: Token mint address
            sell_percentage: Percentage to sell (0-100)
            slippage_bps: Slippage in basis points
            
        Returns:
            Dictionary with sell results
        """
        if not mint_address:
            raise PumpFunValidationError("Mint address cannot be empty")
        if not 0 <= sell_percentage <= 100:
            raise PumpFunValidationError("Sell percentage must be between 0 and 100")
            
        endpoint = "/api/pump/sell-dev"
        data = {
            "mintAddress": mint_address,
            "sellAmountPercentage": f"{sell_percentage}%",
            "slippageBps": slippage_bps
        }
        
        return self._make_request_with_retry("POST", endpoint, json=data)

    def batch_sell_token(self, mint_address: str, sell_percentage: float, 
                        slippage_bps: int = 2500, target_wallet_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Batch sell tokens from multiple wallets (excluding DevWallet).
        
        Args:
            mint_address: Token mint address
            sell_percentage: Percentage to sell (0-100)
            slippage_bps: Slippage in basis points
            target_wallet_names: Optional list of target wallet names
            
        Returns:
            Dictionary with batch sell results
        """
        if not mint_address:
            raise PumpFunValidationError("Mint address cannot be empty")
        if not 0 <= sell_percentage <= 100:
            raise PumpFunValidationError("Sell percentage must be between 0 and 100")
            
        endpoint = "/api/pump/batch-sell"
        data = {
            "mintAddress": mint_address,
            "sellAmountPercentage": f"{sell_percentage}%",
            "slippageBps": slippage_bps
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