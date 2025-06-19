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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Configuration
PUMPFUN_API_BASE_URL = "https://pumpfunapibundler-m0ep.onrender.com"  # Default local API server
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0


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
    image_file_name: str = ""


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
                error_data = response.json() if response.content else {}
                raise PumpFunValidationError(f"Validation error: {error_data.get('error', 'Invalid request')}")
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
        
        for attempt in range(max_retries + 1):
            try:
                return self._make_request(method, endpoint, **kwargs)
            except PumpFunNetworkError as e:
                last_exception = e
                if attempt < max_retries:
                    backoff_time = initial_backoff * (2 ** attempt)
                    logger.warning(f"Network error on attempt {attempt + 1}, retrying in {backoff_time}s: {str(e)}")
                    time.sleep(backoff_time)
                else:
                    logger.error(f"All retry attempts failed: {str(e)}")
            except (PumpFunValidationError, PumpFunApiError) as e:
                # Don't retry validation or API errors
                raise e
                
        raise last_exception

    # Wallet Management Methods

    def create_airdrop_wallet(self, private_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Create or import an airdrop (mother) wallet.
        
        Args:
            private_key: Optional private key for import (base58 string)
            
        Returns:
            Dictionary with wallet details
        """
        endpoint = "/api/wallets/airdrop"
        data = {}
        if private_key:
            data["privateKey"] = private_key
            
        return self._make_request("POST", endpoint, json=data)

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
        
        return self._make_request("POST", endpoint, json=data)

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
            
        endpoint = "/api/wallets/fund-bundled"
        data = {"amountPerWallet": amount_per_wallet}
        
        return self._make_request_with_retry("POST", endpoint, json=data)

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
        Get wallet balance.
        
        Args:
            public_key: Wallet public key
            
        Returns:
            Dictionary with balance information
        """
        if not public_key:
            raise PumpFunValidationError("Public key cannot be empty")
            
        endpoint = f"/api/wallets/{public_key}/balance"
        
        return self._make_request_with_retry("GET", endpoint)

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
        
        return self._make_request_with_retry("POST", endpoint, json=data)

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
        
        Returns:
            Dictionary with health status
        """
        try:
            # Try to get balance of a dummy address to test connectivity
            response = self._make_request("GET", "/api/wallets/11111111111111111111111111111111/balance")
            return {"status": "healthy", "api_reachable": True}
        except Exception as e:
            return {"status": "unhealthy", "api_reachable": False, "error": str(e)}

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