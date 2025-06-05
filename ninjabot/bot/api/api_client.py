import json
import time
from typing import Dict, List, Any, Optional, Callable
import requests
from loguru import logger
from bot.config import API_BASE_URL
import uuid
import hashlib
import random
import asyncio
import os
import re

class ApiClientError(Exception):
    """Base exception for API client errors."""
    pass

class ApiTimeoutError(ApiClientError):
    """Exception raised when an API request times out."""
    pass

class ApiBadResponseError(ApiClientError):
    """Exception raised when the API returns a non-200 status code."""
    pass


class ApiClient:
    """Client for interacting with the backend API."""
    
    def __init__(self, base_url: str = API_BASE_URL, timeout: int = 10):
        """
        Initialize the API client.
        
        Args:
            base_url: The base URL for the API
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        
        # Set to False to use the real API
        self.use_mock = False
        
        # Add correlation ID header for tracing
        self.run_id = None
        
        # Store the latest mother wallet address to avoid creating new ones
        self._latest_mother_wallet = None
        
        # Health check caching
        self._health_check_cache = None
        self._health_check_timestamp = 0
        self._health_check_cache_ttl = 300  # Cache health check results for 5 minutes
        
        # Create data directory if it doesn't exist
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
        os.makedirs(self.data_dir, exist_ok=True)
    
    def set_run_id(self, run_id: str):
        """Set the run ID for tracing purposes."""
        self.run_id = run_id
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make an HTTP request to the API.
        
        Args:
            method: HTTP method (get, post, etc.)
            endpoint: API endpoint
            **kwargs: Additional arguments to pass to requests
            
        Returns:
            The JSON response data
            
        Raises:
            ApiTimeoutError: If the request times out
            ApiBadResponseError: If the API returns a non-200 status code
        """
        url = f"{self.base_url}{endpoint}"
        
        # Set default timeout if not provided
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
        
        # Add headers if not present
        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        
        # Add run_id for tracing if available
        if self.run_id:
            kwargs['headers']['X-Run-Id'] = self.run_id
            
        start_time = time.time()
        
        try:
            logger.debug(
                f"Making {method.upper()} request to {endpoint}",
                extra={
                    "method": method, 
                    "url": url, 
                    "params": kwargs.get('params'),
                    "json": kwargs.get('json'),
                    "tg_user_id": kwargs.get('headers', {}).get('X-User-Id'),
                    "run_id": self.run_id
                }
            )
            
            response = getattr(self.session, method)(url, **kwargs)
            elapsed = time.time() - start_time
            
            logger.debug(
                f"Received response from {endpoint} in {elapsed:.2f}s",
                extra={
                    "status_code": response.status_code, 
                    "elapsed_time": elapsed,
                    "payload_size": len(response.content),
                    "endpoint": endpoint
                }
            )
            
            # For debugging purposes, log the complete response content
            try:
                logger.debug(f"Response content: {response.text}")
            except Exception as e:
                logger.warning(f"Could not log response content: {str(e)}")
            
            # Check for valid status codes:
            # - 200 OK for GET and most operations
            # - 201 Created for POST operations that create new resources
            # - 204 No Content for DELETE operations
            valid_status_codes = [200]
            
            # Add 201 for resource creation (POST)
            if method.lower() == 'post':
                valid_status_codes.append(201)
                
            # Add 204 for resource deletion (DELETE)
            if method.lower() == 'delete':
                valid_status_codes.append(204)
                
            if response.status_code not in valid_status_codes:
                logger.error(
                    f"API error: {response.status_code} {response.text}",
                    extra={"status_code": response.status_code, "response_text": response.text}
                )
                raise ApiBadResponseError(f"API returned {response.status_code}: {response.text}")
                
            # Parse JSON response safely
            try:
                # First try standard JSON parsing
                json_data = response.json()
                return json_data
            except json.JSONDecodeError as e:
                logger.warning(f"Standard JSON parsing failed: {str(e)}")
                
                # As a fallback, try to extract structured data manually
                try:
                    # If response contains key-value patterns, extract them
                    # First check if it looks like JSON (starts with { and ends with })
                    if response.text.strip().startswith('{') and response.text.strip().endswith('}'):
                        # Try to manually extract key-value pairs
                        result = {}
                        # Extract all "key":"value" pairs
                        pattern = r'"([^"]+)"\s*:\s*"([^"]+)"'
                        matches = re.findall(pattern, response.text)
                        for key, value in matches:
                            result[key] = value
                            
                        # Extract numeric values
                        pattern = r'"([^"]+)"\s*:\s*([0-9.]+)'
                        matches = re.findall(pattern, response.text)
                        for key, value in matches:
                            try:
                                result[key] = float(value)
                            except:
                                result[key] = value
                        
                        # Extract boolean values
                        pattern = r'"([^"]+)"\s*:\s*(true|false)'
                        matches = re.findall(pattern, response.text)
                        for key, value in matches:
                            result[key] = (value.lower() == 'true')
                        
                        # Extract array values
                        pattern = r'"([^"]+)"\s*:\s*\[(.*?)\]'
                        matches = re.findall(pattern, response.text, re.DOTALL)
                        for key, value in matches:
                            # Simple handling for arrays - just store as string for now
                            result[key] = value.strip()
                            
                        # If we extracted data, return it
                        if result:
                            logger.info("Successfully extracted data manually from JSON response")
                            return result
                except Exception as manual_error:
                    logger.error(f"Manual JSON extraction failed: {str(manual_error)}")
                
                # If all parsing attempts fail, raise the original error
                logger.error(f"Failed to parse JSON response: {str(e)}")
                logger.error(f"Response text: {response.text}")
                raise ApiClientError(f"Failed to parse JSON response: {str(e)}")
            
        except requests.exceptions.Timeout:
            logger.error(
                f"Request to {url} timed out after {self.timeout}s",
                extra={"endpoint": endpoint, "timeout": self.timeout}
            )
            raise ApiTimeoutError(f"Request to {endpoint} timed out")
            
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Request to {url} failed: {str(e)}",
                extra={"endpoint": endpoint, "error": str(e)}
            )
            raise ApiClientError(f"Request failed: {str(e)}")
    
    def _make_request_with_retry(self, method: str, endpoint: str, max_retries: int = 3, initial_backoff: float = 1.0, **kwargs) -> Dict[str, Any]:
        """
        Make an HTTP request to the API with retry logic for transient failures.
        
        Args:
            method: HTTP method (get, post, etc.)
            endpoint: API endpoint
            max_retries: Maximum number of retry attempts
            initial_backoff: Initial backoff time in seconds
            **kwargs: Additional arguments to pass to requests
            
        Returns:
            The JSON response data
            
        Raises:
            ApiTimeoutError: If all retry attempts time out
            ApiBadResponseError: If the API returns a non-200 status code after all retries
        """
        retries = 0
        backoff = initial_backoff
        
        while True:
            try:
                response = self._make_request(method, endpoint, **kwargs)
                
                # Check if the response contains an error message
                if isinstance(response, dict) and 'message' in response:
                    message = response['message']
                    # Check if the message indicates an error
                    if ('error' in message.lower() or 
                        'missing' in message.lower() or 
                        'invalid' in message.lower() or 
                        'must' in message.lower()):
                        
                        logger.warning(f"API returned warning message: {message}")
                        
                        # For client-side parameter errors, don't retry
                        if ('missing required parameter' in message.lower() or 
                            'invalid parameter' in message.lower() or
                            'each child wallet must' in message.lower()):
                            raise ApiClientError(f"Parameter error: {message}")
                    else:
                        # Just a normal message, log it
                        logger.info(f"API message: {message}")
                
                return response
                
            except (ApiTimeoutError, ApiClientError) as e:
                retries += 1
                
                # Stop if we've reached the maximum number of retries
                if retries >= max_retries:
                    logger.error(f"Failed after {retries} retries: {str(e)}")
                    raise
                
                # Log retry attempt
                logger.warning(
                    f"Request failed, retrying ({retries}/{max_retries}) after {backoff:.2f}s: {str(e)}",
                    extra={"retry_count": retries, "backoff": backoff, "error": str(e)}
                )
                
                # Wait before retrying with exponential backoff
                time.sleep(backoff)
                backoff *= 2  # Exponential backoff
    
    async def _make_request_with_retry_async(self, method: str, endpoint: str, max_retries: int = 3, initial_backoff: float = 1.0, **kwargs) -> Dict[str, Any]:
        """
        Async version of _make_request_with_retry.
        
        Args:
            method: HTTP method (get, post, etc)
            endpoint: API endpoint
            max_retries: Maximum number of retries
            initial_backoff: Initial backoff time in seconds (will be multiplied by 2^retry_count)
            **kwargs: Additional arguments for the request
            
        Returns:
            Response data
            
        Raises:
            ApiClientError: If the request fails after all retries
        """
        # This is an async wrapper for the synchronous method
        # In a full async implementation, the actual request mechanism would be async too
        # But for compatibility, we're just calling the sync method here
        return self._make_request_with_retry(method, endpoint, max_retries, initial_backoff, **kwargs)
    
    def check_api_health(self, mother_wallet_address: str = None) -> Dict[str, Any]:
        """
        Check if the API is responsive and functioning.
        
        Args:
            mother_wallet_address: Optional mother wallet address to check instead of creating a new one
            
        Returns:
            Dictionary with API health information
        
        Raises:
            ApiClientError: If the API health check fails
        """
        # Check if we have a cached health check result that's still valid
        current_time = time.time()
        if (self._health_check_cache is not None and 
            current_time - self._health_check_timestamp < self._health_check_cache_ttl):
            logger.debug("Using cached health check result")
            return self._health_check_cache
            
        # Use provided mother wallet address or the stored one
        mother_wallet_address = mother_wallet_address or self._latest_mother_wallet
        
        if self.use_mock:
            mock_result = {
                "status": "healthy",
                "tokens": {
                    "SOL": "So11111111111111111111111111111111111111112",
                    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    "BTC": "8bMMF9R8xgfXzwZo8SpzqHitas7J3QQtmTRwrKSiJTQa"
                }
            }
            # Cache the result
            self._health_check_cache = mock_result
            self._health_check_timestamp = current_time
            return mock_result
        
        # Try endpoints in order until one succeeds
        endpoints = [
            '/api/health',                # Standard health check
            '/api',                       # Root API path
            '/api/tokens',                # Try tokens endpoint if it exists
            '/api/wallets/health',        # Wallets health check if it exists
            '/api/wallets'                # General wallets endpoint
        ]
        
        for endpoint in endpoints:
            try:
                logger.debug(f"Trying health check with endpoint: {endpoint}")
                response = self._make_request('get', endpoint)
                
                # If we get here, the endpoint worked - check if it has useful data
                if isinstance(response, dict):
                    # Add status field if missing
                    if 'status' not in response:
                        response['status'] = 'healthy'
                        
                    # Add tokens if available or use default SOL
                    if 'tokens' not in response:
                        response['tokens'] = {
                            "SOL": "So11111111111111111111111111111111111111112"
                        }
                        
                    logger.info(f"API health check succeeded using {endpoint}")
                    
                    # Cache the successful health check
                    self._health_check_cache = response
                    self._health_check_timestamp = current_time
                    
                    return response
            except Exception as e:
                logger.debug(f"Health check failed with {endpoint}: {str(e)}")
                continue  # Try next endpoint
                
        # If mother wallet address is provided, check its balance instead of creating a new wallet
        if mother_wallet_address:
            try:
                logger.debug(f"Checking mother wallet balance for health check: {mother_wallet_address}")
                balance_response = self._make_request_with_retry('get', f'/api/wallets/mother/{mother_wallet_address}')
                
                # If we can successfully get the balance, the API is healthy
                if isinstance(balance_response, dict) and 'publicKey' in balance_response:
                    logger.info("API health check succeeded by checking existing wallet balance")
                    
                    health_result = {
                        "status": "healthy",
                        "message": "Health verified via wallet balance check",
                        "tokens": {
                            "SOL": "So11111111111111111111111111111111111111112"
                        }
                    }
                    
                    # Cache the successful health check
                    self._health_check_cache = health_result
                    self._health_check_timestamp = current_time
                    
                    return health_result
            except Exception as e:
                logger.debug(f"Balance check failed for mother wallet: {str(e)}")
        
        # Only create a new wallet as a last resort and only if no mother wallet was provided
        if not mother_wallet_address:
            try:
                logger.debug("Trying to create a mother wallet to check API health")
                wallet_response = self._make_request('post', '/api/wallets/mother')
                
                # If wallet creation works, the API is healthy
                if isinstance(wallet_response, dict) and (
                    'motherWalletPublicKey' in wallet_response or 
                    'error' not in wallet_response
                ):
                    logger.info("API health check succeeded by creating a wallet")
                    
                    health_result = {
                        "status": "healthy",
                        "message": "Health verified via wallet creation",
                        "tokens": {
                            "SOL": "So11111111111111111111111111111111111111112"
                        }
                    }
                    
                    # Cache the successful health check
                    self._health_check_cache = health_result
                    self._health_check_timestamp = current_time
                    
                    return health_result
            except Exception as e:
                logger.warning(f"Final health check attempt failed: {str(e)}")
        
        # If all checks fail, return a fallback response for testing
        logger.warning("All health checks failed, using fallback response")
        
        fallback_result = {
            "status": "error",
            "message": "Could not verify API health",
            "tokens": {
                "SOL": "So11111111111111111111111111111111111111112"
            }
        }
        
        # Cache the fallback result but with a shorter TTL
        self._health_check_cache = fallback_result
        self._health_check_timestamp = current_time
        self._health_check_cache_ttl = 60  # Shorter TTL for error results (1 minute)
        
        return fallback_result
            
    def direct_call(self, method: str, endpoint: str, **kwargs):
        """
        Make a direct API call and return the raw response text.
        This bypasses JSON parsing issues that might be happening.
        
        Args:
            method: HTTP method (get, post, etc.)
            endpoint: API endpoint
            **kwargs: Additional arguments to pass to requests
            
        Returns:
            Raw response object from requests
        """
        url = f"{self.base_url}{endpoint}"
        
        # Set default timeout if not provided
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
        
        # Add headers if not present
        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        
        # Add run_id for tracing if available
        if self.run_id:
            kwargs['headers']['X-Run-Id'] = self.run_id
            
        start_time = time.time()
        
        try:
            logger.debug(f"Making direct {method.upper()} request to {endpoint}")
            
            response = getattr(self.session, method)(url, **kwargs)
            elapsed = time.time() - start_time
            
            logger.debug(f"Received direct response from {endpoint} in {elapsed:.2f}s")
            
            # Check for valid status codes:
            # - 200 OK for GET and most operations
            # - 201 Created for POST operations that create new resources
            # - 204 No Content for DELETE operations
            valid_status_codes = [200]
            
            # Add 201 for resource creation (POST)
            if method.lower() == 'post':
                valid_status_codes.append(201)
                
            # Add 204 for resource deletion (DELETE)
            if method.lower() == 'delete':
                valid_status_codes.append(204)
                
            if response.status_code not in valid_status_codes:
                logger.error(f"API error in direct call: {response.status_code}")
                return None
                
            return response
            
        except Exception as e:
            logger.error(f"Direct request failed: {str(e)}")
            return None

    def get_jupiter_quote(self, input_mint: str, output_mint: str, amount: int, 
                         slippage_bps: int = 50, only_direct_routes: bool = False,
                         as_legacy_transaction: bool = False, platform_fee_bps: int = 0) -> Dict[str, Any]:
        """
        Get a swap quote from Jupiter DEX.
        
        Args:
            input_mint: Token mint address of the input token or symbol (SOL, USDC, etc.)
            output_mint: Token mint address of the output token or symbol (SOL, USDC, etc.)
            amount: Amount of input token in base units (e.g., lamports for SOL)
            slippage_bps: Slippage tolerance in basis points (default: 50)
            only_direct_routes: Whether to only use direct swap routes (default: False)
            as_legacy_transaction: Whether to use legacy transactions (default: False)
            platform_fee_bps: Platform fee in basis points (default: 0)
            
        Returns:
            Dictionary containing Jupiter quote response
            
        Raises:
            ApiClientError: If the quote request fails
        """
        if self.use_mock:
            # Mock realistic Jupiter quote data for testing
            import random
            
            # Simulate different output amounts based on input
            base_rate = 0.98  # Simulate 2% price impact base
            variation = random.uniform(-0.02, 0.02)  # ±2% variation
            output_amount = int(amount * (base_rate + variation))
            
            mock_quote = {
                "message": "Jupiter quote retrieved successfully",
                "quoteResponse": {
                    "inputMint": input_mint,
                    "outputMint": output_mint,
                    "inAmount": str(amount),
                    "outAmount": str(output_amount),
                    "amount": str(amount),
                    "otherAmountThreshold": str(int(output_amount * 0.98)),
                    "swapMode": "ExactIn",
                    "slippageBps": slippage_bps,
                    "platformFee": None if platform_fee_bps == 0 else {"amount": str(int(amount * platform_fee_bps / 10000)), "feeBps": platform_fee_bps},
                    "priceImpactPct": str(round(random.uniform(0.1, 2.0), 2)),
                    "routePlan": [
                        {
                            "swapInfo": {
                                "ammKey": "mock_amm_key",
                                "label": "Mock DEX",
                                "inputMint": input_mint,
                                "outputMint": output_mint,
                                "inAmount": str(amount),
                                "outAmount": str(output_amount),
                                "feeAmount": str(int(amount * 0.003)),  # 0.3% fee
                                "feeMint": input_mint
                            },
                            "percent": 100
                        }
                    ],
                    "_formattedInfo": {
                        "inputToken": input_mint,
                        "outputToken": output_mint,
                        "inputAmount": f"{amount / 1000000000} SOL" if input_mint == "SOL" else str(amount),
                        "outputAmount": f"{output_amount / 1000000000} SOL" if output_mint == "SOL" else str(output_amount),
                        "priceImpactPct": round(random.uniform(0.1, 2.0), 2),
                        "routeSteps": 1
                    }
                }
            }
            
            logger.info(f"Mock Jupiter quote: {amount} {input_mint} → {output_amount} {output_mint}")
            return mock_quote
        
        # Prepare the request payload
        payload = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount,
            "slippageBps": slippage_bps,
            "onlyDirectRoutes": only_direct_routes,
            "asLegacyTransaction": as_legacy_transaction,
            "platformFeeBps": platform_fee_bps
        }
        
        logger.info(f"Requesting Jupiter quote: {amount} {input_mint} → {output_mint} (slippage: {slippage_bps}bps)")
        
        try:
            # Use existing retry mechanism with extended timeout for DEX operations
            original_timeout = self.timeout
            self.timeout = max(self.timeout, 20)  # DEX quotes can take longer
            
            response = self._make_request_with_retry(
                'post',
                '/api/jupiter/quote',
                json=payload,
                max_retries=3,
                initial_backoff=1.0
            )
            
            # Restore original timeout
            self.timeout = original_timeout
            
            # Validate response structure
            if not isinstance(response, dict):
                raise ApiClientError("Invalid response format from Jupiter quote API")
            
            if "quoteResponse" not in response:
                error_msg = response.get("message", "Unknown error in Jupiter quote response")
                raise ApiClientError(f"Jupiter quote failed: {error_msg}")
            
            # Log successful quote retrieval
            quote_data = response["quoteResponse"]
            input_amount = quote_data.get("inAmount", "unknown")
            output_amount = quote_data.get("outAmount", "unknown")
            price_impact = quote_data.get("priceImpactPct", "unknown")
            
            logger.info(f"Jupiter quote successful: {input_amount} {input_mint} → {output_amount} {output_mint} (impact: {price_impact}%)")
            
            return response
            
        except (ApiTimeoutError, ApiBadResponseError) as e:
            logger.error(f"Jupiter quote API error: {str(e)}")
            raise ApiClientError(f"Failed to get Jupiter quote: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in Jupiter quote: {str(e)}")
            raise ApiClientError(f"Jupiter quote request failed: {str(e)}")
        finally:
            # Ensure timeout is restored even if an exception occurs
            self.timeout = original_timeout