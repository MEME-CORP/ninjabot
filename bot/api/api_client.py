import json
import time
from typing import Dict, List, Any, Optional, Callable
import requests
from loguru import logger
from bot.config import API_BASE_URL

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
        
        # For simplicity in this implementation, we'll use a mock API
        # In a real implementation, this would be replaced with actual API calls
        self.use_mock = True
    
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
            
        start_time = time.time()
        
        try:
            logger.debug(
                f"Making {method.upper()} request to {endpoint}",
                extra={
                    "method": method, 
                    "url": url, 
                    "params": kwargs.get('params'),
                    "json": kwargs.get('json')
                }
            )
            
            response = getattr(self.session, method)(url, **kwargs)
            elapsed = time.time() - start_time
            
            logger.debug(
                f"Received response from {endpoint} in {elapsed:.2f}s",
                extra={"status_code": response.status_code, "elapsed_time": elapsed}
            )
            
            if response.status_code != 200:
                logger.error(
                    f"API error: {response.status_code} {response.text}",
                    extra={"status_code": response.status_code, "response_text": response.text}
                )
                raise ApiBadResponseError(f"API returned {response.status_code}: {response.text}")
                
            return response.json()
            
        except requests.exceptions.Timeout:
            logger.error(f"Request to {url} timed out after {self.timeout}s")
            raise ApiTimeoutError(f"Request to {endpoint} timed out")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request to {url} failed: {str(e)}")
            raise ApiClientError(f"Request failed: {str(e)}")
    
    def create_wallet(self) -> Dict[str, Any]:
        """
        Create a new mother wallet.
        
        Returns:
            Wallet information including address
        """
        if self.use_mock:
            return {
                "address": "5XYzRxaKLTJeH3fMMD5Xyc9umzmFXmgHYVnxnhx6hzwY",
                "created_at": time.time()
            }
            
        return self._make_request('post', '/wallet/create')
    
    def import_wallet(self, private_key: str) -> Dict[str, Any]:
        """
        Import a wallet using private key.
        
        Args:
            private_key: Wallet private key
            
        Returns:
            Wallet information including address
        """
        if self.use_mock:
            return {
                "address": "7xB1sGUFR2hjyVw8SVdTXSCYQodÜ8RJx3xTkzwUwPc",
                "imported": True
            }
            
        return self._make_request('post', '/wallet/import', json={"private_key": private_key})
    
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
            return [
                {"address": f"Child{i}Wallet{int(time.time())%10000}", "index": i}
                for i in range(n)
            ]
            
        return self._make_request(
            'post', 
            '/wallet/derive_children', 
            json={"mother_wallet": mother_wallet, "count": n}
        )
    
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
            
        return self._make_request(
            'post', 
            '/schedule', 
            json={
                "mother_wallet": mother_wallet,
                "child_wallets": child_wallets,
                "token_address": token_address,
                "total_volume": total_volume
            }
        )
    
    def check_balance(self, wallet_address: str, token_address: str) -> Dict[str, Any]:
        """
        Check wallet balance for a token.
        
        Args:
            wallet_address: Wallet address to check
            token_address: Token contract address
            
        Returns:
            Balance information
        """
        if self.use_mock:
            # Simulate balance checks with randomized values for testing
            import random
            
            # 20% chance of having sufficient balance for testing
            has_balance = random.random() < 0.2
            
            if has_balance:
                return {
                    "wallet": wallet_address,
                    "token": token_address,
                    "balance": random.uniform(1000, 10000),
                    "timestamp": time.time()
                }
            else:
                return {
                    "wallet": wallet_address,
                    "token": token_address,
                    "balance": random.uniform(0, 100),
                    "timestamp": time.time()
                }
            
        return self._make_request(
            'get', 
            '/balance', 
            params={"wallet": wallet_address, "token": token_address}
        )
    
    def start_execution(self, run_id: str) -> Dict[str, Any]:
        """
        Start executing a schedule.
        
        Args:
            run_id: The schedule run ID
            
        Returns:
            Execution status
        """
        if self.use_mock:
            return {
                "run_id": run_id,
                "status": "started",
                "started_at": time.time()
            }
            
        return self._make_request('post', f'/run/{run_id}/start')

# Create a singleton instance
api_client = ApiClient() 