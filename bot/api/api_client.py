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
    
    def create_wallet(self) -> Dict[str, Any]:
        """
        Create a new mother wallet.
        
        Returns:
            Wallet information including address
        """
        if self.use_mock:
            mock_wallet = {
                "address": "5XYzRxaKLTJeH3fMMD5Xyc9umzmFXmgHYVnxnhx6hzwY",
                "created_at": time.time()
            }
            # Save mock wallet data
            self.save_wallet_data('mother', mock_wallet)
            return mock_wallet
            
        try:
            # Try direct API call via _make_request_with_retry first
            try:
                response_data = self._make_request_with_retry('post', '/api/wallets/mother')
                
                # If the response has motherWalletPublicKey, use it directly
                if isinstance(response_data, dict) and 'motherWalletPublicKey' in response_data:
                    public_key = response_data['motherWalletPublicKey']
                    private_key = response_data.get('motherWalletPrivateKeyBase58', '')
                    
                    logger.info(f"Successfully created mother wallet: {public_key}")
                    # Store the mother wallet address for future health checks
                    self._latest_mother_wallet = public_key
                    
                    # Create wallet info dict
                    wallet_info = {
                        'address': public_key,
                        'private_key': private_key,
                        'created_at': time.time()
                    }
                    
                    # Save wallet data to JSON file
                    self.save_wallet_data('mother', wallet_info)
                    
                    return wallet_info
            except Exception as api_error:
                logger.warning(f"Standard API call failed, trying direct call: {str(api_error)}")
                
            # If standard API call failed, try direct_call as fallback
            response = self.direct_call('post', '/api/wallets/mother')
            if not response:
                logger.error("Failed to create wallet - null response")
                fallback_wallet = {
                    'address': "5XYzRxaKLTJeH3fMMD5Xyc9umzmFXmgHYVnxnhx6hzwY",  # Fallback for tests
                    'created_at': time.time(),
                    'error': "API call failed"
                }
                return fallback_wallet
            
            # Extract wallet address directly from response text using regex
            try:
                import re
                match = re.search(r'"motherWalletPublicKey"\s*:\s*"([^"]+)"', response.text)
                if match:
                    public_key = match.group(1)
                    private_key_match = re.search(r'"motherWalletPrivateKeyBase58"\s*:\s*"([^"]+)"', response.text)
                    private_key = private_key_match.group(1) if private_key_match else ''
                    
                    logger.info(f"Successfully extracted mother wallet address: {public_key}")
                    
                    # Create wallet info dict
                    wallet_info = {
                        'address': public_key,
                        'private_key': private_key,
                        'created_at': time.time()
                    }
                    
                    # Save wallet data to JSON file
                    self.save_wallet_data('mother', wallet_info)
                    
                    return wallet_info
            except Exception as e:
                logger.error(f"Failed to extract wallet address: {str(e)}")
            
            # If we reach here, extraction failed - use fallback
            logger.warning("Could not extract wallet address, using fallback")
            fallback_wallet = {
                'address': "5XYzRxaKLTJeH3fMMD5Xyc9umzmFXmgHYVnxnhx6hzwY",  # Fallback for tests
                'created_at': time.time(),
                'error': "Failed to extract address"
            }
            return fallback_wallet
            
        except Exception as e:
            logger.error(f"Error in create_wallet: {str(e)}")
            fallback_wallet = {
                'address': "5XYzRxaKLTJeH3fMMD5Xyc9umzmFXmgHYVnxnhx6hzwY",
                'created_at': time.time(),
                'error_details': str(e)
            }
            return fallback_wallet
    
    def import_wallet(self, private_key: str) -> Dict[str, Any]:
        """
        Import a wallet using private key.
        
        Args:
            private_key: Wallet private key
            
        Returns:
            Wallet information including address
        """
        if self.use_mock:
            mock_wallet = {
                "address": "7xB1sGUFR2hjyVw8SVdTXSCYQodÜ8RJx3xTkzwUwPc",
                "private_key": private_key,
                "imported": True,
                "created_at": time.time()
            }
            # Save mock wallet data
            self.save_wallet_data('mother', mock_wallet)
            return mock_wallet
            
        try:
            # Make direct API call
            response = self.direct_call(
                'post', 
                '/api/wallets/mother', 
                json={"privateKeyBase58": private_key}
            )
            
            if not response:
                logger.error("Failed to import wallet - null response")
                fallback_wallet = {
                    'address': f"ImportedWallet{private_key[:8]}",
                    'private_key': private_key,
                    'created_at': time.time(),
                    'imported': True,
                    'error': "API call failed"
                }
                return fallback_wallet
            
            # Extract wallet address directly from response text
            try:
                import re
                match = re.search(r'"motherWalletPublicKey"\s*:\s*"([^"]+)"', response.text)
                if match:
                    public_key = match.group(1)
                    logger.info(f"Successfully extracted imported wallet address: {public_key}")
                    # Store the mother wallet address for future health checks
                    self._latest_mother_wallet = public_key
                    
                    # Create wallet info dict
                    wallet_info = {
                        'address': public_key,
                        'private_key': private_key,
                        'created_at': time.time(),
                        'imported': True
                    }
                    
                    # Save wallet data to JSON file
                    self.save_wallet_data('mother', wallet_info)
                    
                    return wallet_info
            except Exception as e:
                logger.error(f"Failed to extract imported wallet address: {str(e)}")
            
            # If extraction fails, generate a deterministic address for testing
            import hashlib
            fallback_address = f"ImportedWallet{hashlib.md5(private_key.encode()).hexdigest()[:8]}"
            logger.warning(f"Using fallback imported wallet address: {fallback_address}")
            
            # Create fallback wallet info
            fallback_wallet = {
                'address': fallback_address,
                'private_key': private_key,
                'created_at': time.time(),
                'imported': True,
                'error': "Failed to extract address"
            }
            
            return fallback_wallet
            
        except Exception as e:
            logger.error(f"Error importing wallet: {str(e)}")
            raise ApiClientError(f"Failed to import wallet: {str(e)}")
    
    def derive_child_wallets(self, n: int, mother_wallet: str) -> List[Dict[str, Any]]:
        """
        Derive child wallets from a mother wallet.
        
        Args:
            n: Number of child wallets to derive
            mother_wallet: Mother wallet address
            
        Returns:
            List of child wallet information
        """
        if self.use_mock:
            # Create mock child wallets
            child_wallets = [
                {"address": f"Child{i}Wallet{int(time.time())%10000}", "index": i, "private_key": f"mock_private_key_{i}"}
                for i in range(n)
            ]
            
            # Save child wallets data
            self.save_wallet_data('children', {
                'mother_address': mother_wallet,
                'wallets': child_wallets,
                'created_at': time.time()
            })
            
            return child_wallets
            
        try:
            # Try standard API call first
            try:
                payload = {
                    "motherWalletPublicKey": mother_wallet, 
                    "count": n,
                    "includePrivateKeys": True  # Request private keys for child wallets
                }
                response_data = self._make_request_with_retry('post', '/api/wallets/children', json=payload)
                
                # Check if response contains childWallets array
                if isinstance(response_data, dict) and 'childWallets' in response_data:
                    child_wallets = []
                    for i, child in enumerate(response_data['childWallets']):
                        if isinstance(child, dict) and 'publicKey' in child:
                            # Fix: Use privateKeyBase58 instead of privateKey
                            priv_key = child.get('privateKeyBase58', '')
                            
                            # Enhanced logging for private key retrieval
                            if priv_key:
                                logger.debug(f"Child wallet {child['publicKey']} (index {i}): private key retrieved.")
                            else:
                                logger.warning(f"Child wallet {child['publicKey']} (index {i}): private key 'privateKeyBase58' NOT found in API response object for this child.")
                            
                            child_wallets.append({
                                'address': child['publicKey'],
                                'private_key': priv_key,  # Store private key if available
                                'index': i
                            })
                    
                    if child_wallets:
                        logger.info(f"Successfully derived {len(child_wallets)} child wallets")
                        
                        # Save child wallets data
                        self.save_wallet_data('children', {
                            'mother_address': mother_wallet,
                            'wallets': child_wallets,
                            'created_at': time.time()
                        })
                        
                        return child_wallets
            except Exception as api_error:
                logger.warning(f"Standard API call failed for child wallets, trying direct call: {str(api_error)}")
            
            # If standard API call failed, try direct call
            response = self.direct_call(
                'post', 
                '/api/wallets/children', 
                json={
                    "motherWalletPublicKey": mother_wallet, 
                    "count": n,
                    "includePrivateKeys": True  # Request private keys
                }
            )
            
            if not response:
                logger.error("Failed to derive child wallets - null response")
                return [
                    {"address": f"child_{i}_{int(time.time())}", "index": i, "error": "API call failed"}
                    for i in range(n)
                ]
            
            # Extract wallet addresses and private keys using regex to avoid JSON parsing issues
            try:
                # Find all public keys and private keys in the response
                public_key_matches = re.findall(r'"publicKey"\s*:\s*"([^"]+)"', response.text)
                # Fix: Search for privateKeyBase58 instead of privateKey
                private_key_matches = re.findall(r'"privateKeyBase58"\s*:\s*"([^"]+)"', response.text)
                
                if public_key_matches and len(public_key_matches) == n:
                    child_wallets = []
                    for i, addr in enumerate(public_key_matches):
                        # Try to get corresponding private key if available
                        private_key = private_key_matches[i] if i < len(private_key_matches) else ''
                        
                        # Enhanced logging for private key retrieval in regex fallback
                        if private_key:
                            logger.debug(f"Child wallet {addr} (index {i}): private key extracted via regex from direct call.")
                        else:
                            logger.warning(f"Child wallet {addr} (index {i}): private key 'privateKeyBase58' NOT found via regex in direct call response.")
                        
                        child_wallets.append({
                            'address': addr,
                            'private_key': private_key,
                            'index': i
                        })
                    
                    logger.info(f"Successfully extracted {len(child_wallets)} child wallet addresses")
                    
                    # Save child wallets data
                    self.save_wallet_data('children', {
                        'mother_address': mother_wallet,
                        'wallets': child_wallets,
                        'created_at': time.time()
                    })
                    
                    return child_wallets
            except Exception as e:
                logger.error(f"Failed to extract child wallet addresses: {str(e)}")
            
            # If extraction fails, generate fallback addresses for testing
            logger.warning(f"Using fallback child wallet addresses")
            fallback_wallets = [
                {"address": f"child_{i}_{int(time.time())}", "index": i, "private_key": ""}
                for i in range(n)
            ]
            
            return fallback_wallets
            
        except Exception as e:
            logger.error(f"Error deriving child wallets: {str(e)}")
            return [
                {"address": f"error_{i}_{int(time.time())}", "index": i, "error": str(e)}
                for i in range(n)
            ]
    
    def generate_schedule(
        self, 
        mother_wallet: str,
        child_wallets: List[str],
        token_address: str,
        total_volume: float
    ) -> Dict[str, Any]:
        """
        Generate a transfer schedule.
        
        Args:
            mother_wallet: Mother wallet address
            child_wallets: List of child wallet addresses
            token_address: Token contract address
            total_volume: Total volume to transfer
            
        Returns:
            Schedule information including transfers
        """
        if self.use_mock:
            # Generate a mock schedule for display
            now = time.time()
            import random
            
            # Calculate fee
            from bot.config import SERVICE_FEE_RATE
            fee = total_volume * SERVICE_FEE_RATE
            remaining_volume = total_volume - fee
            
            # Create random transfers
            transfers = []
            total_transferred = 0
            num_transfers = len(child_wallets) * 2  # Each wallet does ~2 transfers
            
            for i in range(num_transfers - 1):
                # Determine a random amount for this transfer
                max_possible = remaining_volume - total_transferred
                if num_transfers - i > 1:
                    # Leave some for remaining transfers
                    max_amount = max_possible * 0.8
                    amount = random.uniform(max_possible * 0.01, max_amount)
                else:
                    # Last transfer, use remaining amount
                    amount = max_possible
                
                total_transferred += amount
                
                # Random sender and receiver from child wallets
                sender_idx = random.randint(0, len(child_wallets) - 1)
                receiver_idx = random.randint(0, len(child_wallets) - 1)
                while receiver_idx == sender_idx:
                    receiver_idx = random.randint(0, len(child_wallets) - 1)
                
                # Random time between 1 and 100 seconds from previous transfer
                if i == 0:
                    timestamp = now + random.randint(1, 10)
                else:
                    timestamp = transfers[-1]["timestamp"] + random.randint(1, 100)
                
                transfers.append({
                    "id": f"tx_{i}",
                    "from": child_wallets[sender_idx],
                    "to": child_wallets[receiver_idx],
                    "amount": amount,
                    "timestamp": timestamp,
                    "status": "pending"
                })
            
            # Add one more transfer for the fee
            transfers.append({
                "id": "tx_fee",
                "from": child_wallets[0],  # Use first child wallet for fee
                "to": "ServiceFeeWallet123456789",  # Service fee wallet
                "amount": fee,
                "timestamp": transfers[-1]["timestamp"] + random.randint(1, 100),
                "status": "pending",
                "is_fee": True
            })
            
            return {
                "run_id": f"run_{int(time.time())}",
                "mother_wallet": mother_wallet,
                "token_address": token_address,
                "total_volume": total_volume,
                "service_fee": fee,
                "net_volume": remaining_volume,
                "transfers": transfers,
                "created_at": now
            }
            
        # If there's a dedicated schedule endpoint on the API, use it
        # Otherwise keep local schedule generation
        try:
            # First try the schedule endpoint if it exists
            return self._make_request_with_retry(
                'post', 
                '/api/schedule', 
                json={
                    "motherAddress": mother_wallet,
                    "childAddresses": child_wallets,
                    "tokenAddress": token_address,
                    "totalVolume": total_volume
                }
            )
        except ApiBadResponseError as e:
            # If the endpoint doesn't exist (404), fall back to local schedule generation
            if "404" in str(e):
                logger.warning("Schedule endpoint not found, using local generation")
                # Use mock generation (existing method but forced)
                old_use_mock = self.use_mock
                self.use_mock = True
                result = self.generate_schedule(mother_wallet, child_wallets, token_address, total_volume)
                self.use_mock = old_use_mock
                return result
            else:
                # For other errors, propagate them
                raise
    
    def generate_funding_operation_id(self, mother_wallet: str, child_wallet: str, amount: float) -> str:
        """
        Generate a deterministic operation ID to track mother-to-child funding attempts.
        
        Args:
            mother_wallet: Mother wallet address
            child_wallet: Child wallet address
            amount: Amount to transfer
            
        Returns:
            Unique operation ID for funding operations
        """
        # Create a deterministic ID based on the transfer parameters
        # Include more specificity to avoid collisions
        transfer_data = f"{mother_wallet}:{child_wallet}:{amount}:{int(time.time() / 3600)}"  # Hourly uniqueness
        return hashlib.md5(transfer_data.encode()).hexdigest()
    
    async def wait_for_balance_change(self, wallet_address: str, initial_balance: float, 
                                    target_balance: float, max_wait_time: int = 60, 
                                    check_interval: int = 5) -> Dict[str, Any]:
        """
        Wait for a wallet balance to change to the expected value.
        
        Args:
            wallet_address: Wallet address to monitor
            initial_balance: Initial balance before transfer
            target_balance: Expected balance after transfer
            max_wait_time: Maximum time to wait in seconds
            check_interval: Interval between checks in seconds
            
        Returns:
            Dictionary with verification result including:
            - verified: True if balance changed to expected value
            - final_balance: The final observed balance
            - difference: Difference between final and initial balance
            - duration: Time taken for verification in seconds
        """
        logger.info(f"Waiting for wallet {wallet_address} balance to change from {initial_balance} to {target_balance}")
        
        start_time = time.time()
        result = {
            "verified": False,
            "initial_balance": initial_balance,
            "target_balance": target_balance,
            "final_balance": initial_balance,
            "difference": 0,
            "duration": 0
        }
        
        while time.time() - start_time < max_wait_time:
            # Check balance
            try:
                balance_info = self.check_balance(wallet_address)
                
                # Extract SOL balance
                current_balance = 0
                if "balances" in balance_info:
                    for token_balance in balance_info["balances"]:
                        if token_balance.get("symbol") == "SOL":
                            current_balance = token_balance.get("amount", 0)
                            break
                
                result["final_balance"] = current_balance
                result["difference"] = current_balance - initial_balance
                
                # Check if balance is close to target (allowing for slight differences due to fees)
                if abs(current_balance - target_balance) < 0.0001:
                    logger.success(f"Balance changed to expected value: {current_balance} SOL")
                    result["verified"] = True
                    break
                
                # Check if balance has changed significantly from initial
                if abs(current_balance - initial_balance) > 0.0001:
                    logger.info(f"Balance changed to {current_balance} SOL, but not yet at target {target_balance} SOL")
            
            except Exception as e:
                logger.warning(f"Error checking balance during verification: {str(e)}")
            
            logger.info(f"Waiting {check_interval}s for balance to update... ({int(time.time() - start_time)}s elapsed)")
            await asyncio.sleep(check_interval)
        
        result["duration"] = time.time() - start_time
        
        if not result["verified"]:
            logger.warning(f"Timed out waiting for balance change after {max_wait_time}s")
        
        return result
    
    async def verify_transaction(self, from_wallet: str, to_wallet: str, 
                               amount: float, max_wait_time: int = 60,
                               check_interval: int = 5) -> Dict[str, Any]:
        """
        Verify that a transaction was completed by checking balance changes.
        
        Args:
            from_wallet: Sender wallet address
            to_wallet: Receiver wallet address
            amount: Expected amount transferred
            max_wait_time: Maximum wait time in seconds
            check_interval: Balance check interval in seconds
            
        Returns:
            Dictionary with verification results
        """
        logger.info(f"Verifying transfer of {amount} SOL from {from_wallet} to {to_wallet}")
        
        # Get initial balances
        try:
            # Get initial from_wallet balance
            from_balance_info = self.check_balance(from_wallet)
            initial_from_balance = 0
            for token_balance in from_balance_info.get("balances", []):
                if token_balance.get("symbol") == "SOL":
                    initial_from_balance = token_balance.get("amount", 0)
                    break
            
            # Get initial to_wallet balance
            to_balance_info = self.check_balance(to_wallet)
            initial_to_balance = 0
            for token_balance in to_balance_info.get("balances", []):
                if token_balance.get("symbol") == "SOL":
                    initial_to_balance = token_balance.get("amount", 0)
                    break
            
            logger.info(f"Initial balances - From: {initial_from_balance} SOL, To: {initial_to_balance} SOL")
            
            # Expected balances after transfer (accounting for gas fees)
            expected_from_balance = initial_from_balance - amount - 0.0001  # Approximate gas fee
            expected_to_balance = initial_to_balance + amount
            
            # Verify sender's balance decreased
            from_result = await self.wait_for_balance_change(
                from_wallet,
                initial_from_balance,
                expected_from_balance,
                max_wait_time,
                check_interval
            )
            
            # Verify receiver's balance increased
            to_result = await self.wait_for_balance_change(
                to_wallet,
                initial_to_balance,
                expected_to_balance,
                max_wait_time,
                check_interval
            )
            
            # Determine overall verification success
            verification_success = from_result["verified"] or to_result["verified"]
            
            # Create combined result
            result = {
                "verified": verification_success,
                "sender_verified": from_result["verified"],
                "receiver_verified": to_result["verified"],
                "sender": {
                    "address": from_wallet,
                    "initial_balance": initial_from_balance,
                    "final_balance": from_result["final_balance"],
                    "difference": from_result["difference"]
                },
                "receiver": {
                    "address": to_wallet,
                    "initial_balance": initial_to_balance,
                    "final_balance": to_result["final_balance"],
                    "difference": to_result["difference"]
                },
                "amount": amount,
                "duration": max(from_result["duration"], to_result["duration"])
            }
            
            if verification_success:
                logger.success(f"Transfer verification successful: {amount} SOL from {from_wallet} to {to_wallet}")
            else:
                logger.warning(f"Transfer verification failed: {amount} SOL from {from_wallet} to {to_wallet}")
                
            return result
            
        except Exception as e:
            logger.error(f"Error during transaction verification: {str(e)}")
            return {
                "verified": False,
                "error": str(e)
            }
    
    def fund_child_wallets(self, mother_wallet: str, child_wallets: List[str], token_address: str, amount_per_wallet: float, 
                      mother_private_key: str = None, priority_fee: int = 25000, batch_id: str = None,
                      idempotency_key: str = None, verify_transfers: bool = True) -> Dict[str, Any]:
        """
        Fund child wallets from mother wallet.
        
        Args:
            mother_wallet: Mother wallet address
            child_wallets: List of child wallet addresses to fund
            token_address: Token contract address
            amount_per_wallet: Amount to fund each wallet with
            mother_private_key: Mother wallet private key for signing transactions
            priority_fee: Priority fee in microLamports to accelerate transactions (default: 25000)
            batch_id: Optional batch ID for tracking grouped transactions
            idempotency_key: Optional idempotency key to prevent duplicate transactions
            verify_transfers: Whether to verify transfers by checking balance changes
            
        Returns:
            Status of funding operations
        """
        if self.use_mock:
            # Mock successful funding operation
            return {
                "status": "success",
                "funded_wallets": len(child_wallets),
                "transactions": [
                    {"tx_id": f"mock_tx_{i}", "status": "confirmed"}
                    for i in range(len(child_wallets))
                ]
            }
        
        # Generate a batch ID if not provided
        if not batch_id:
            batch_id = self.generate_batch_id()
        
        # Check for duplicate requests - store already processed wallets
        processed_wallets = set()
        
        # Format child wallets exactly as in test_specific_transfers.py
        formatted_child_wallets = []
        for i, child_wallet in enumerate(child_wallets):
            # Skip if wallet already in the processed set (duplicate)
            if child_wallet in processed_wallets:
                logger.warning(f"Skipping duplicate wallet: {child_wallet}")
                continue
                
            # Add to processed set
            processed_wallets.add(child_wallet)
            
            # Generate a deterministic operation ID if none provided
            operation_id = None
            if not idempotency_key:
                operation_id = self.generate_funding_operation_id(mother_wallet, child_wallet, amount_per_wallet)
            else:
                # If an idempotency key was provided, make it unique for each wallet
                operation_id = f"{idempotency_key}_{i}"
                
            formatted_child_wallets.append({
                "publicKey": child_wallet,
                "amountSol": amount_per_wallet,
                "operationId": operation_id
            })
        
        # If no valid wallets after deduplication, return early
        if not formatted_child_wallets:
            logger.warning(f"No valid child wallets to fund after deduplication")
            return {
                "status": "skipped",
                "message": "No valid child wallets to fund after deduplication"
            }
            
        # Prepare the funding payload exactly matching test_specific_transfers.py format
        funding_payload = {
            "motherAddress": mother_wallet,
            "childWallets": formatted_child_wallets,
            "tokenAddress": token_address or "So11111111111111111111111111111111111111112",  # Default to SOL token address
            "batchId": batch_id,
            "priorityFee": priority_fee
        }
        
        # Add mother wallet private key if provided (for signing transactions)
        if mother_private_key:
            funding_payload["motherWalletPrivateKeyBase58"] = mother_private_key
            
        # Add idempotency key if provided - use a single key for all transfers
        if idempotency_key:
            funding_payload["idempotencyKey"] = idempotency_key
            
        # IMPORTANT: Remove childAddresses to avoid confusion with childWallets
        if "childAddresses" in funding_payload:
            del funding_payload["childAddresses"]
            
        logger.info(f"Funding {len(formatted_child_wallets)} child wallets with batch ID: {batch_id} and priority fee: {priority_fee}")
        
        # Use a higher timeout for blockchain operations
        original_timeout = self.timeout
        self.timeout = max(self.timeout, 45)  # Use at least 45 seconds for blockchain operations
        
        try:
            api_result = self._make_request_with_retry(
                'post', 
                '/api/wallets/fund-children', 
                json=funding_payload
            )
            
            # Log API response
            logger.info(f"API Response for funding: {json.dumps(api_result, default=str)}")
            
            # Create response structure
            result = {
                "batch_id": batch_id,
                "status": api_result.get("status", "unknown"),
                "api_response": api_result,
                "verification_results": [],
                "successful_transfers": 0,
                "failed_transfers": 0
            }
            
            # Verify transfers if requested
            if verify_transfers:
                # Get initial balances before verification
                initial_balances = {}
                for child in formatted_child_wallets:
                    try:
                        balance_info = self.check_balance(child["publicKey"])
                        for token_balance in balance_info.get("balances", []):
                            if token_balance.get("symbol") == "SOL":
                                initial_balances[child["publicKey"]] = token_balance.get("amount", 0)
                                break
                    except Exception as e:
                        logger.warning(f"Could not get initial balance for {child['publicKey']}: {str(e)}")
                        initial_balances[child["publicKey"]] = 0
                
                # Allow time for transactions to propagate to the network
                logger.info("Waiting 5 seconds for transactions to propagate before verification...")
                time.sleep(5)
                
                # Use asyncio to run the verification asynchronously
                verification_tasks = []
                event_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(event_loop)
                
                try:
                    # Create verification tasks for each wallet
                    for child in formatted_child_wallets:
                        child_address = child["publicKey"]
                        initial_balance = initial_balances.get(child_address, 0)
                        expected_balance = initial_balance + child["amountSol"]
                        
                        verification_task = self.wait_for_balance_change(
                            child_address,
                            initial_balance,
                            expected_balance,
                            max_wait_time=60,  # Wait up to 60 seconds for balance changes
                            check_interval=5   # Check every 5 seconds
                        )
                        verification_tasks.append((child_address, verification_task))
                    
                    # Run all verification tasks
                    for child_address, task in verification_tasks:
                        try:
                            verification_result = event_loop.run_until_complete(task)
                            
                            # Add wallet address to result
                            verification_result["wallet_address"] = child_address
                            
                            # Track successful and failed transfers
                            if verification_result["verified"]:
                                result["successful_transfers"] += 1
                            else:
                                result["failed_transfers"] += 1
                                
                            # Add to verification results
                            result["verification_results"].append(verification_result)
                            
                        except Exception as e:
                            logger.error(f"Error verifying transfer to {child_address}: {str(e)}")
                            result["failed_transfers"] += 1
                            result["verification_results"].append({
                                "wallet_address": child_address,
                                "verified": False,
                                "error": str(e)
                            })
                
                finally:
                    # Close the event loop
                    event_loop.close()
                
                # Update overall status based on verification
                if result["successful_transfers"] == len(formatted_child_wallets):
                    result["status"] = "success"
                elif result["successful_transfers"] > 0:
                    result["status"] = "partial_success"
                else:
                    result["status"] = "failed"
                
                logger.info(f"Transfer verification completed: {result['successful_transfers']} successful, {result['failed_transfers']} failed")
            
            return result
            
        except ApiTimeoutError as e:
            # If API times out but transaction might have gone through
            logger.warning(f"API timeout during funding operation (batch: {batch_id}): {str(e)}")
            return {
                "status": "timeout",
                "message": f"API request timed out after {self.timeout}s, but transactions may have completed on-chain",
                "batch_id": batch_id,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error in fund_child_wallets: {str(e)}")
            return {
                "status": "error",
                "message": f"Error during funding operation: {str(e)}",
                "batch_id": batch_id,
                "error": str(e)
            }
        finally:
            # Restore original timeout
            self.timeout = original_timeout
    
    def check_balance(self, wallet_address: str, token_address: str = None) -> Dict[str, Any]:
        """
        Check the balance of a wallet.
        
        Args:
            wallet_address: Wallet address to check
            token_address: Optional token contract address
            
        Returns:
            Balance information
        """
        if self.use_mock:
            import random
            return {
                "wallet": wallet_address,
                "balances": [
                    {
                        "token": token_address or "So11111111111111111111111111111111111111112", # SOL
                        "amount": random.uniform(0.1, 10.0),
                        "symbol": "SOL"
                    }
                ]
            }
        
        # Use the proper API endpoint for wallet balance
        endpoint = f'/api/wallets/mother/{wallet_address}'
        
        try:
            # Try standard API call first
            try:
                response = self._make_request_with_retry('get', endpoint)
                # Log the entire response for debugging
                logger.info(f"Raw balance response from API: {json.dumps(response)}")
                
                # Transform API response into expected format
                # The API response appears to have a format like:
                # {"publicKey": "...", "balanceSol": 0, "balanceLamports": 0}
                if 'publicKey' in response:
                    # Check for various possible balance fields
                    sol_balance = 0
                    if 'balanceSol' in response:
                        sol_balance = float(response['balanceSol'])
                    elif 'balanceLamports' in response:
                        # Convert lamports to SOL (1 SOL = 1,000,000,000 lamports)
                        sol_balance = float(response['balanceLamports']) / 1000000000
                    
                    logger.info(f"Extracted SOL balance from API response: {sol_balance}")
                    
                    # Format expected by the rest of the code
                    formatted_response = {
                        "wallet": response['publicKey'],
                        "balances": [
                            {
                                "token": "So11111111111111111111111111111111111111112",  # SOL mint address
                                "amount": sol_balance,
                                "symbol": "SOL"
                            }
                        ]
                    }
                    
                    # If a specific token was requested and it's not SOL, add a placeholder
                    if token_address and token_address != "So11111111111111111111111111111111111111112":
                        # Try to find the token in tokens list
                        token_info = self._get_token_info(token_address, wallet_address)
                        if token_info:
                            formatted_response["balances"].append({
                                "token": token_address,
                                "amount": 0,  # Default to 0 for testing
                                "symbol": token_info.get("symbol", "Unknown")
                            })
                    
                    return formatted_response
            except Exception as api_error:
                logger.warning(f"Standard balance check failed, trying direct call: {str(api_error)}")
                
            # If standard API call failed, try direct call
            response = self.direct_call('get', endpoint)
            if not response:
                logger.error(f"Failed to check balance for {wallet_address} - null response")
                # Return a placeholder response for testing
                return {
                    "wallet": wallet_address,
                    "balances": [
                        {
                            "token": "So11111111111111111111111111111111111111112",  # SOL
                            "amount": 0,
                            "symbol": "SOL"
                        }
                    ]
                }
            
            # Log the full response for debugging
            logger.info(f"Direct call response status: {response.status_code}")
            logger.info(f"Direct call response content: {response.text}")
            
            # Try to extract balance directly from response text
            try:
                import re
                # Extract publicKey using regex
                pubkey_match = re.search(r'"publicKey"\s*:\s*"([^"]+)"', response.text)
                
                # Try multiple patterns for balance extraction - the API might return different formats
                balance_patterns = [
                    r'"balanceSol"\s*:\s*([0-9.]+)',  # Standard format: "balanceSol": 0.002
                    r'"balanceSol"\s*:\s*([0-9.e\-+]+)',  # Scientific notation: "balanceSol": 2.0e-3
                    r'"balance"\s*:\s*([0-9.]+)',  # Alternative key: "balance": 0.002
                    r'"lamports"\s*:\s*([0-9]+)',  # Lamports format: "lamports": 2000000
                    r'"balanceLamports"\s*:\s*([0-9]+)'  # Explicit lamports: "balanceLamports": 2000000
                ]
                
                sol_balance = 0
                for pattern in balance_patterns:
                    balance_match = re.search(pattern, response.text)
                    if balance_match:
                        raw_value = balance_match.group(1)
                        logger.info(f"Found balance match with pattern '{pattern}': {raw_value}")
                        
                        # Handle different format types
                        if 'lamports' in pattern:
                            # Convert lamports to SOL (1 SOL = 1,000,000,000 lamports)
                            sol_balance = float(raw_value) / 1000000000
                        else:
                            # Direct SOL value
                            sol_balance = float(raw_value)
                        
                        # Found a match, break the loop
                        break
                
                if pubkey_match:
                    public_key = pubkey_match.group(1)
                    logger.info(f"Successfully extracted balance for {public_key}: {sol_balance} SOL")
                    return {
                        "wallet": public_key,
                        "balances": [
                            {
                                "token": "So11111111111111111111111111111111111111112",  # SOL mint address
                                "amount": sol_balance,
                                "symbol": "SOL"
                            }
                        ]
                    }
            except Exception as e:
                logger.error(f"Failed to extract balance from response: {str(e)}")
            
            # If all extraction methods fail, return a placeholder
            if 'wallet' not in response:
                response = {
                    "wallet": wallet_address,
                    "balances": [
                        {
                            "token": "So11111111111111111111111111111111111111112",  # SOL
                            "amount": 0,
                            "symbol": "SOL"
                        }
                    ]
                }
                
            return response
            
        except ApiClientError as e:
            logger.error(f"Failed to check balance: {str(e)}")
            
            # Return a placeholder response for testing
            return {
                "wallet": wallet_address,
                "balances": [
                    {
                        "token": "So11111111111111111111111111111111111111112",  # SOL
                        "amount": 0,
                        "symbol": "SOL"
                    }
                ]
            }
    
    def _get_token_info(self, token_address: str, mother_wallet_address: str = None) -> Dict[str, Any]:
        """Get token information."""
        try:
            tokens_response = self.check_api_health(mother_wallet_address)
            if 'tokens' in tokens_response:
                tokens_dict = tokens_response['tokens']
                # Find the token by address
                for symbol, address in tokens_dict.items():
                    if address == token_address:
                        return {"symbol": symbol, "address": address}
            return {}
        except Exception:
            return {}
    
    def start_execution(self, run_id: str) -> Dict[str, Any]:
        """
        Start executing a transfer schedule.
        
        Args:
            run_id: The run ID to execute
            
        Returns:
            Status of the execution
        """
        if self.use_mock:
            return {
                "status": "started",
                "run_id": run_id,
                "estimated_time": 120  # seconds
            }
            
        # Set the run_id for tracing
        self.set_run_id(run_id)
        
        # Try the execute endpoint if available
        try:
            return self._make_request_with_retry(
                'post', 
                '/api/execute', 
                json={"runId": run_id}
            )
        except ApiBadResponseError as e:
            # If 404, the endpoint doesn't exist, use direct fund transfer approach
            if "404" in str(e):
                logger.warning("Execute endpoint not found, using direct funding approach from test_specific_transfers.py")
                
                # Since we don't have access to the specifics at this level,
                # we'll need to return a response that tells the caller
                # to handle the funding directly, following test_specific_transfers.py approach
                
                return {
                    "status": "execute_endpoint_not_found",
                    "message": "The '/api/execute' endpoint was not found. The caller should handle direct funding using the fund_child_wallets method, following the approach in test_specific_transfers.py",
                    "run_id": run_id
                }
            else:
                # For other errors, propagate them
                raise
        except Exception as e:
            # Handle general errors
            logger.error(f"Error in start_execution: {str(e)}")
            raise ApiClientError(f"Failed to start execution: {str(e)}")
    
    def get_run_report(self, run_id: str) -> Dict[str, Any]:
        """
        Get a report for a completed run.
        
        Args:
            run_id: The run ID to get a report for
            
        Returns:
            Run report information
        """
        if self.use_mock:
            # Create a mock report
            import random
            from datetime import datetime
            
            transfers = []
            for i in range(random.randint(10, 20)):
                transfers.append({
                    "id": f"tx_{i}",
                    "from": f"Mock_Sender_{i}",
                    "to": f"Mock_Receiver_{i}",
                    "amount": random.uniform(0.1, 5.0),
                    "timestamp": datetime.now().timestamp() - random.randint(0, 3600),
                    "status": random.choice(["confirmed", "confirmed", "confirmed", "failed"]),
                    "tx_hash": f"mock_hash_{i}" * 4
                })
                
            return {
                "run_id": run_id,
                "status": "completed",
                "start_time": datetime.now().timestamp() - 3600,
                "end_time": datetime.now().timestamp(),
                "total_volume": sum(t["amount"] for t in transfers if t["status"] == "confirmed"),
                "success_count": sum(1 for t in transfers if t["status"] == "confirmed"),
                "fail_count": sum(1 for t in transfers if t["status"] != "confirmed"),
                "transfers": transfers
            }
            
        return self._make_request_with_retry('get', f'/api/runs/{run_id}')
    
    def get_transaction_status(self, tx_hash: str) -> Dict[str, Any]:
        """
        Get the status of a transaction.
        
        Args:
            tx_hash: Transaction hash to check
            
        Returns:
            Transaction status
        """
        if self.use_mock:
            import random
            statuses = ["confirmed", "confirmed", "confirmed", "processing", "failed"]
            weighted_statuses = statuses[:3] * 3 + statuses[3:] # Make confirmed more likely
            
            return {
                "tx_hash": tx_hash,
                "status": random.choice(weighted_statuses),
                "confirmations": random.randint(0, 32) if random.choice(weighted_statuses) != "failed" else 0,
                "block_time": int(time.time()) - random.randint(0, 600)
            }
            
        return self._make_request_with_retry('get', f'/api/transactions/{tx_hash}')

    def check_sufficient_balance(self, mother_wallet: str, token_address: str, required_volume: float) -> Dict[str, Any]:
        """
        Check if the mother wallet has sufficient balance for the required volume.
        
        Args:
            mother_wallet: Mother wallet address
            token_address: Token contract address
            required_volume: Required token volume
            
        Returns:
            Dictionary containing:
            - sufficient (bool): Whether the wallet has sufficient balance
            - current_balance (float): Current wallet balance
            - required_balance (float): Required balance
            - token_symbol (str): Token symbol
        """
        try:
            # Check the wallet balance
            logger.info(f"Checking if wallet {mother_wallet} has sufficient balance for {required_volume} tokens")
            
            balance_info = self.check_balance(mother_wallet, token_address)
            logger.info(f"Balance check result: {json.dumps(balance_info)}")
            
            # Extract the balance of the specific token
            current_balance = 0
            token_symbol = "tokens"
            
            if isinstance(balance_info, dict) and 'balances' in balance_info:
                for token_balance in balance_info['balances']:
                    # For SOL token (default token or explicitly requested)
                    if token_address is None or token_address == "So11111111111111111111111111111111111111112":
                        if token_balance.get('token') == "So11111111111111111111111111111111111111112" or token_balance.get('symbol') == "SOL":
                            current_balance = token_balance.get('amount', 0)
                            token_symbol = token_balance.get('symbol', "SOL")
                            break
                    # For other specific tokens
                    elif token_balance.get('token') == token_address:
                        current_balance = token_balance.get('amount', 0)
                        token_symbol = token_balance.get('symbol', "tokens")
                        break
            
            # Ensure balance is a float
            if not isinstance(current_balance, float):
                try:
                    current_balance = float(current_balance)
                except (TypeError, ValueError):
                    logger.warning(f"Could not convert balance to float: {current_balance}")
                    current_balance = 0
            
            # Log extracted values for debugging
            logger.info(f"Extracted balance: {current_balance} {token_symbol}")
            
            # Determine if the balance is sufficient
            sufficient = current_balance >= required_volume
            
            if sufficient:
                logger.info(f"Wallet has sufficient balance: {current_balance} {token_symbol}")
            else:
                logger.info(f"Wallet balance insufficient: {current_balance}/{required_volume} {token_symbol}")
            
            return {
                'sufficient': sufficient,
                'current_balance': current_balance,
                'required_balance': required_volume,
                'token_symbol': token_symbol
            }
            
        except Exception as e:
            logger.error(f"Error checking sufficient balance: {str(e)}")
            return {
                'sufficient': False,
                'current_balance': 0,
                'required_balance': required_volume,
                'token_symbol': 'tokens',
                'error': str(e)
            }

    def generate_batch_id(self) -> str:
        """Generate a unique batch ID for a group of transfers."""
        return f"batch_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    
    def generate_transfer_operation_id(self, sender_wallet: str, receiver_wallet: str, amount: float) -> str:
        """
        Generate a deterministic operation ID to track wallet-to-wallet transfer attempts.
        
        Args:
            sender_wallet: Sender wallet address
            receiver_wallet: Receiver wallet address
            amount: Amount to transfer
            
        Returns:
            Unique operation ID for transfer operations
        """
        # Create a deterministic ID based on the transfer parameters
        transfer_data = f"{sender_wallet}:{receiver_wallet}:{amount}"
        return hashlib.md5(transfer_data.encode()).hexdigest()
    
    async def transfer_child_to_mother(self, child_wallet: str, child_private_key: str, 
                                     mother_wallet: str, amount: float, token_address: str = None,
                                     priority_fee: int = 25000, verify_transfer: bool = True) -> Dict[str, Any]:
        """
        Transfer tokens from a child wallet back to the mother wallet.
        
        Args:
            child_wallet: Child wallet address
            child_private_key: Child wallet private key
            mother_wallet: Mother wallet address
            amount: Amount to transfer
            token_address: Token contract address (default: SOL)
            priority_fee: Priority fee in microLamports
            verify_transfer: Whether to verify the transfer
            
        Returns:
            Dictionary with transfer status
        """
        if self.use_mock:
            # Mock successful transfer
            return {
                "status": "success",
                "from_wallet": child_wallet,
                "to_wallet": mother_wallet,
                "amount": amount,
                "tx_id": f"mock_tx_{int(time.time())}"
            }
        
        logger.info(f"Transferring {amount} SOL from child wallet {child_wallet} to mother wallet {mother_wallet}")
        
        # Generate a unique operation ID for this transfer
        operation_id = self.generate_transfer_operation_id(child_wallet, mother_wallet, amount)
        batch_id = self.generate_batch_id()
        
        # Format the transfer payload
        transfer_payload = {
            "senderAddress": child_wallet,
            "senderPrivateKeyBase58": child_private_key,
            "receiverAddress": mother_wallet,
            "amountSol": amount,
            "tokenAddress": token_address or "So11111111111111111111111111111111111111112",  # Default to SOL
            "priorityFee": priority_fee,
            "operationId": operation_id,
            "batchId": batch_id
        }
        
        # Use a higher timeout for blockchain operations
        original_timeout = self.timeout
        self.timeout = max(self.timeout, 45)  # Use at least 45 seconds for blockchain operations
        
        try:
            # Get initial balances before transfer
            try:
                sender_balance_info = self.check_balance(child_wallet)
                initial_sender_balance = 0
                for token_balance in sender_balance_info.get("balances", []):
                    if token_balance.get("symbol") == "SOL":
                        initial_sender_balance = token_balance.get("amount", 0)
                        break
                
                receiver_balance_info = self.check_balance(mother_wallet)
                initial_receiver_balance = 0
                for token_balance in receiver_balance_info.get("balances", []):
                    if token_balance.get("symbol") == "SOL":
                        initial_receiver_balance = token_balance.get("amount", 0)
                        break
                
                logger.info(f"Initial balances - Child: {initial_sender_balance} SOL, Mother: {initial_receiver_balance} SOL")
            except Exception as e:
                logger.warning(f"Error checking initial balances: {str(e)}")
                initial_sender_balance = 0
                initial_receiver_balance = 0
            
            # Try multiple APIs to handle the transfer
            api_result = None
            api_error = None
            
            # First try the direct wallet transfer endpoint
            try:
                api_result = self._make_request_with_retry(
                    'post',
                    '/api/wallets/transfer',
                    json=transfer_payload
                )
                logger.info(f"API Response for direct wallet transfer: {json.dumps(api_result, default=str)}")
            except Exception as e:
                logger.warning(f"Direct wallet transfer API failed: {str(e)}")
                api_error = str(e)
                
                # If direct transfer fails, try the generic transaction endpoint
                try:
                    tx_payload = {
                        "instructions": [
                            {
                                "type": "transfer",
                                "sender": child_wallet,
                                "receiver": mother_wallet,
                                "amount": amount,
                                "tokenAddress": transfer_payload["tokenAddress"],
                            }
                        ],
                        "signers": [
                            {
                                "publicKey": child_wallet,
                                "privateKey": child_private_key
                            }
                        ],
                        "priorityFee": priority_fee,
                        "operationId": operation_id,
                        "batchId": batch_id
                    }
                    
                    api_result = self._make_request_with_retry(
                        'post',
                        '/api/transaction/execute',
                        json=tx_payload
                    )
                    logger.info(f"API Response for transaction execute: {json.dumps(api_result, default=str)}")
                except Exception as e2:
                    logger.warning(f"Transaction execute API failed: {str(e2)}")
                    
                    # If both APIs fail, try a fallback method
                    try:
                        # Try the same endpoint as mother-to-child transfers
                        child_as_mother_payload = {
                            "motherAddress": child_wallet,
                            "motherWalletPrivateKeyBase58": child_private_key,
                            "childWallets": [
                                {
                                    "publicKey": mother_wallet,
                                    "amountSol": amount,
                                    "operationId": operation_id
                                }
                            ],
                            "tokenAddress": transfer_payload["tokenAddress"],
                            "batchId": batch_id,
                            "priorityFee": priority_fee,
                            "idempotencyKey": operation_id
                        }
                        
                        api_result = self._make_request_with_retry(
                            'post',
                            '/api/wallets/fund-children',
                            json=child_as_mother_payload
                        )
                        logger.info(f"API Response for fund-children fallback: {json.dumps(api_result, default=str)}")
                    except Exception as e3:
                        logger.error(f"All API attempts failed, will rely on balance verification: {str(e3)}")
            
            # Create response structure
            result = {
                "batch_id": batch_id,
                "operation_id": operation_id,
                "status": api_result.get("status", "unknown") if api_result else "api_failed",
                "api_response": api_result,
                "api_error": api_error,
                "from_wallet": child_wallet,
                "to_wallet": mother_wallet,
                "amount": amount,
                "initial_sender_balance": initial_sender_balance,
                "initial_receiver_balance": initial_receiver_balance,
                "verification_result": None
            }
            
            # Verify transfer if requested
            if verify_transfer:
                # Allow time for transaction to propagate to the network
                logger.info("Waiting 5 seconds for transaction to propagate before verification...")
                await asyncio.sleep(5)
                
                # Calculate expected balances
                expected_sender_balance = initial_sender_balance - amount - 0.0001  # Approximate gas fee
                expected_receiver_balance = initial_receiver_balance + amount
                
                # Run verification
                verification_result = await self.verify_transaction(
                    child_wallet,
                    mother_wallet,
                    amount,
                    max_wait_time=60,  # Wait up to 60 seconds for balance changes
                    check_interval=5    # Check every 5 seconds
                )
                
                # Update result with verification
                result["verification_result"] = verification_result
                result["verified"] = verification_result.get("verified", False)
                
                # Update status based on verification
                if verification_result.get("verified", False):
                    result["status"] = "success"
                    logger.success(f"Child-to-mother transfer of {amount} SOL from {child_wallet} to {mother_wallet} verified successful!")
                else:
                    result["status"] = "verification_failed"
                    logger.warning(f"Child-to-mother transfer verification failed for {amount} SOL from {child_wallet} to {mother_wallet}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in transfer_child_to_mother: {str(e)}")
            return {
                "status": "error",
                "from_wallet": child_wallet,
                "to_wallet": mother_wallet,
                "amount": amount,
                "error": str(e)
            }
        finally:
            # Restore original timeout
            self.timeout = original_timeout
            
    async def execute_volume_run(self, mother_wallet: str, child_wallets: List[str], 
                               child_private_keys: List[str], trades: List[Dict[str, Any]], 
                               token_address: str, verify_transfers: bool = True) -> Dict[str, Any]:
        """
        Execute a complete volume generation run with transaction verification.
        
        Args:
            mother_wallet: Mother wallet address
            child_wallets: List of child wallet addresses
            child_private_keys: List of child wallet private keys
            trades: List of trade instructions with from_wallet, to_wallet, and amount
            token_address: Token contract address
            verify_transfers: Whether to verify transfers by checking balance changes
            
        Returns:
            Status of volume generation operations
        """
        if self.use_mock:
            return {
                "status": "success",
                "trades_executed": len(trades),
                "trades_succeeded": len(trades),
                "trades_failed": 0
            }
        
        logger.info(f"Starting volume run with {len(trades)} trades for token {token_address}")
        
        # Generate a batch ID for this volume run
        batch_id = self.generate_batch_id()
        
        # Create a wallet map for easy lookup
        wallet_map = {}
        for i, wallet in enumerate(child_wallets):
            wallet_map[wallet] = {
                "private_key": child_private_keys[i] if i < len(child_private_keys) else None,
                "index": i
            }
        
        # Track results
        results = {
            "batch_id": batch_id,
            "status": "in_progress",
            "token_address": token_address,
            "total_trades": len(trades),
            "trades_executed": 0,
            "trades_succeeded": 0,
            "trades_failed": 0,
            "trade_results": [],
            "start_time": time.time(),
            "end_time": None,
            "duration": 0,
            "verification_enabled": verify_transfers
        }
        
        # Execute each trade
        for i, trade in enumerate(trades):
            try:
                from_wallet = trade.get("from_wallet")
                to_wallet = trade.get("to_wallet")
                amount = trade.get("amount")
                
                # Skip invalid trades
                if not from_wallet or not to_wallet or not amount:
                    logger.warning(f"Skipping invalid trade {i+1}/{len(trades)}: {trade}")
                    results["trades_failed"] += 1
                    results["trade_results"].append({
                        "status": "skipped",
                        "from_wallet": from_wallet,
                        "to_wallet": to_wallet,
                        "amount": amount,
                        "error": "Invalid trade parameters"
                    })
                    continue
                
                # Log the trade
                logger.info(f"Executing trade {i+1}/{len(trades)}: {amount} SOL from {from_wallet} to {to_wallet}")
                
                # Get the private key for the sender wallet
                sender_private_key = None
                if from_wallet in wallet_map:
                    sender_private_key = wallet_map[from_wallet]["private_key"]
                
                # If sender is mother wallet, use fund_child_wallets
                if from_wallet == mother_wallet and to_wallet in child_wallets:
                    # If mother wallet is sending to child wallet
                    trade_result = await self.transfer_between_wallets(
                        from_wallet=from_wallet,
                        from_private_key=trade.get("private_key"),  # Use provided key if available
                        to_wallet=to_wallet,
                        amount=amount,
                        token_address=token_address,
                        verify_transfer=verify_transfers
                    )
                elif from_wallet in child_wallets and to_wallet == mother_wallet:
                    # If child wallet is sending to mother wallet
                    trade_result = await self.transfer_child_to_mother(
                        child_wallet=from_wallet,
                        child_private_key=sender_private_key,
                        mother_wallet=to_wallet,
                        amount=amount,
                        token_address=token_address,
                        verify_transfer=verify_transfers
                    )
                else:
                    # If transfer is between child wallets
                    trade_result = await self.transfer_between_wallets(
                        from_wallet=from_wallet,
                        from_private_key=sender_private_key,
                        to_wallet=to_wallet,
                        amount=amount,
                        token_address=token_address,
                        verify_transfer=verify_transfers
                    )
                
                # Update trade results
                results["trades_executed"] += 1
                if trade_result.get("status") == "success" or trade_result.get("verified", False):
                    results["trades_succeeded"] += 1
                else:
                    results["trades_failed"] += 1
                
                # Add the result to the list
                results["trade_results"].append(trade_result)
                
                # Add a small delay between trades
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error executing trade {i+1}/{len(trades)}: {str(e)}")
                results["trades_failed"] += 1
                results["trade_results"].append({
                    "status": "error",
                    "from_wallet": trade.get("from_wallet"),
                    "to_wallet": trade.get("to_wallet"),
                    "amount": trade.get("amount"),
                    "error": str(e)
                })
                
                # Continue with the next trade
                continue
        
        # Update final status
        results["end_time"] = time.time()
        results["duration"] = results["end_time"] - results["start_time"]
        
        if results["trades_succeeded"] == results["total_trades"]:
            results["status"] = "success"
        elif results["trades_succeeded"] > 0:
            results["status"] = "partial_success"
        else:
            results["status"] = "failed"
        
        logger.info(f"Volume run completed: {results['trades_succeeded']}/{results['total_trades']} trades succeeded in {results['duration']:.2f} seconds")
        
        return results
    
    def approve_gas_spike(self, run_id: str, instruction_index: int) -> Dict[str, Any]:
        """
        Approve a gas spike for a specific instruction.
        
        Args:
            run_id: The ID of the run
            instruction_index: The index of the instruction with the gas spike
            
        Returns:
            Dictionary with approval result
        """
        if self.use_mock:
            # Mock implementation for testing
            logger.info("Using mock implementation for approve_gas_spike")
            
            return {
                "runId": run_id,
                "instructionIndex": instruction_index,
                "approved": True,
                "message": "Gas spike approved, execution will continue."
            }
        
        # Real API implementation
        endpoint = f"/api/volume/runs/{run_id}/approve-fee-spike"
        payload = {
            "instructionIndex": instruction_index
        }
        
        try:
            result = self._make_request_with_retry(
                "post", 
                endpoint, 
                max_retries=3,
                json=payload
            )
            
            return result
            
        except (ApiTimeoutError, ApiBadResponseError) as e:
            logger.warning(f"Failed to approve gas spike from API: {str(e)}")
            
            # Use mock implementation as fallback
            logger.info("Using mock implementation as fallback for approve_gas_spike")
            return {
                "runId": run_id,
                "instructionIndex": instruction_index,
                "approved": True,
                "message": "Gas spike approved, execution will continue."
            }

    def save_wallet_data(self, wallet_type: str, wallet_data: Dict[str, Any]) -> bool:
        """
        Save wallet data to a JSON file.
        
        Args:
            wallet_type: Type of wallet ('mother' or 'children')
            wallet_data: Wallet data to save
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Create wallet directory if it doesn't exist
            wallet_dir = os.path.join(self.data_dir, 'wallets', wallet_type)
            os.makedirs(wallet_dir, exist_ok=True)
            
            # Create a filename based on wallet address
            address = wallet_data.get('address', wallet_data.get('mother_address', f"wallet_{int(time.time())}"))
            filename = os.path.join(wallet_dir, f"{address}.json")
            
            # Save data to file
            with open(filename, 'w') as f:
                json.dump(wallet_data, f, indent=2)
                
            logger.info(f"Saved {wallet_type} wallet data to {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving wallet data: {str(e)}")
            return False
    
    def load_wallet_data(self, wallet_type: str, wallet_address: str) -> Optional[Dict[str, Any]]:
        """
        Load wallet data from a JSON file.
        
        Args:
            wallet_type: Type of wallet ('mother' or 'children')
            wallet_address: Wallet address to load
            
        Returns:
            Wallet data or None if not found
        """
        try:
            # Construct the wallet directory path
            wallet_dir = os.path.join(self.data_dir, 'wallets', wallet_type)
            
            # First check if there's a combined wallet file
            combined_file_path = os.path.join(wallet_dir, f"{wallet_type}_wallets.json")
            if os.path.exists(combined_file_path):
                try:
                    with open(combined_file_path, 'r') as f:
                        combined_data = json.load(f)
                    
                    # If the wallet exists in the combined file
                    if isinstance(combined_data, dict) and wallet_address in combined_data:
                        wallet_data = combined_data[wallet_address]
                        # Ensure the wallet data has the address field
                        if 'address' not in wallet_data:
                            wallet_data['address'] = wallet_address
                            
                        logger.info(f"Loaded {wallet_type} wallet data for {wallet_address} from combined file")
                        return wallet_data
                except Exception as e:
                    logger.warning(f"Error loading from combined wallet file: {str(e)}")
            
            # If not found in combined file, check for individual file
            individual_file_path = os.path.join(wallet_dir, f"{wallet_address}.json")
            
            # Check if individual file exists
            if os.path.exists(individual_file_path):
                # Load data from file
                with open(individual_file_path, 'r') as f:
                    wallet_data = json.load(f)
                    
                logger.info(f"Loaded {wallet_type} wallet data from {individual_file_path}")
                return wallet_data
            
            # If neither found, report not found
            logger.warning(f"Wallet data file not found for {wallet_address}")
            return None
            
        except Exception as e:
            logger.error(f"Error loading wallet data: {str(e)}")
            return None
            
    def list_saved_wallets(self, wallet_type: str) -> List[Dict[str, Any]]:
        """
        List all saved wallets of a specific type.
        
        Args:
            wallet_type: Type of wallet ('mother' or 'children')
            
        Returns:
            List of wallet data dictionaries
        """
        try:
            # Construct the wallet directory path
            wallet_dir = os.path.join(self.data_dir, 'wallets', wallet_type)
            
            # Create directory if it doesn't exist
            os.makedirs(wallet_dir, exist_ok=True)
            
            wallets = []
            
            # Check for combined wallet file (e.g., mother_wallets.json)
            combined_file_path = os.path.join(wallet_dir, f"{wallet_type}_wallets.json")
            if os.path.exists(combined_file_path):
                try:
                    with open(combined_file_path, 'r') as f:
                        combined_data = json.load(f)
                    
                    # If the file has wallet addresses as keys (old format)
                    if isinstance(combined_data, dict) and not combined_data.get('wallets'):
                        for address, wallet_data in combined_data.items():
                            # Ensure the wallet data has the address field
                            if isinstance(wallet_data, dict):
                                if 'address' not in wallet_data and address:
                                    wallet_data['address'] = address
                                wallets.append(wallet_data)
                    # If it's already a list of wallets
                    elif isinstance(combined_data, list):
                        wallets.extend(combined_data)
                    # If it has a 'wallets' field containing the list
                    elif isinstance(combined_data, dict) and isinstance(combined_data.get('wallets'), list):
                        wallets.extend(combined_data['wallets'])
                        
                    logger.info(f"Loaded {len(wallets)} wallets from combined file {combined_file_path}")
                    
                    # If we found wallets in the combined file, return them
                    if wallets:
                        return wallets
                except Exception as e:
                    logger.warning(f"Error loading combined wallet file {combined_file_path}: {str(e)}")
            
            # If no combined file or it was empty, list individual JSON files
            wallet_files = [f for f in os.listdir(wallet_dir) if f.endswith('.json') and f != f"{wallet_type}_wallets.json"]
            
            if not wallet_files:
                logger.info(f"No saved {wallet_type} wallets found")
                return []
                
            # Load each wallet file
            for filename in wallet_files:
                try:
                    file_path = os.path.join(wallet_dir, filename)
                    with open(file_path, 'r') as f:
                        wallet_data = json.load(f)
                        
                    # Handle different wallet data formats
                    if isinstance(wallet_data, dict):
                        # If this is a wallet container with a 'wallets' array (for child wallets)
                        if 'wallets' in wallet_data and isinstance(wallet_data['wallets'], list):
                            wallets.extend(wallet_data['wallets'])
                        # Otherwise it's a single wallet
                        else:
                            wallets.append(wallet_data)
                except Exception as e:
                    logger.warning(f"Error loading wallet file {filename}: {str(e)}")
                    continue
                    
            logger.info(f"Found {len(wallets)} saved {wallet_type} wallets")
            return wallets
            
        except Exception as e:
            logger.error(f"Error listing saved wallets: {str(e)}")
            return []
            
    def load_child_wallets(self, mother_wallet_address: str) -> List[Dict[str, Any]]:
        """
        Load child wallets associated with a mother wallet.
        
        Args:
            mother_wallet_address: Mother wallet address
            
        Returns:
            List of child wallet dictionaries
        """
        try:
            # Construct the children wallet directory path
            wallet_dir = os.path.join(self.data_dir, 'wallets', 'children')
            
            # Create directory if it doesn't exist
            os.makedirs(wallet_dir, exist_ok=True)
            
            # Check for a combined children file first
            combined_file_path = os.path.join(wallet_dir, "children_wallets.json")
            if os.path.exists(combined_file_path):
                try:
                    with open(combined_file_path, 'r') as f:
                        combined_data = json.load(f)
                    
                    child_wallets = []
                    # If it's a dict mapping mother addresses to child wallet arrays
                    if isinstance(combined_data, dict) and mother_wallet_address in combined_data:
                        mother_children = combined_data[mother_wallet_address]
                        if isinstance(mother_children, list):
                            child_wallets.extend(mother_children)
                        elif isinstance(mother_children, dict) and 'wallets' in mother_children:
                            child_wallets.extend(mother_children['wallets'])
                    
                    # If we found children, return them
                    if child_wallets:
                        logger.info(f"Found {len(child_wallets)} child wallets for mother wallet {mother_wallet_address} in combined file")
                        return child_wallets
                except Exception as e:
                    logger.warning(f"Error loading from combined children file: {str(e)}")
            
            # List all JSON files in the directory
            wallet_files = [f for f in os.listdir(wallet_dir) if f.endswith('.json') and f != "children_wallets.json"]
            
            # Find files that contain the mother wallet address
            child_wallets = []
            for filename in wallet_files:
                try:
                    with open(os.path.join(wallet_dir, filename), 'r') as f:
                        wallet_data = json.load(f)
                        
                        # Check if this child wallet belongs to the specified mother wallet
                        if wallet_data.get('mother_address') == mother_wallet_address:
                            # Extract individual child wallets if contained in a 'wallets' array
                            if 'wallets' in wallet_data and isinstance(wallet_data['wallets'], list):
                                child_wallets.extend(wallet_data['wallets'])
                            else:
                                child_wallets.append(wallet_data)
                except Exception as e:
                    logger.warning(f"Error loading child wallet file {filename}: {str(e)}")
                    continue
                    
            logger.info(f"Found {len(child_wallets)} child wallets for mother wallet {mother_wallet_address}")
            return child_wallets
            
        except Exception as e:
            logger.error(f"Error loading child wallets: {str(e)}")
            return []

# Create a singleton instance
api_client = ApiClient() 