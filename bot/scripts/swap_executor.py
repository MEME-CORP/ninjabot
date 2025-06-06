"""
Swap execution module for SPL Token Buy/Sell Script.
Handles individual wallet swap execution with error handling and verification.
"""

import asyncio
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger
from .buy_sell_config import ExecutionConfig, TokenConfig


class SwapStatus(Enum):
    """Status of a swap operation."""
    PENDING = "pending"
    QUOTE_REQUESTED = "quote_requested"
    QUOTE_RECEIVED = "quote_received"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


@dataclass
class SwapAttempt:
    """Details of a swap attempt."""
    attempt_number: int
    start_time: float
    end_time: Optional[float] = None
    status: SwapStatus = SwapStatus.PENDING
    error: Optional[str] = None
    transaction_id: Optional[str] = None
    quote_data: Optional[Dict[str, Any]] = None
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate attempt duration."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


@dataclass
class SwapResult:
    """Complete result of a swap operation."""
    wallet_address: str
    wallet_index: int
    wallet_private_key: str
    
    # Input parameters
    input_token: str
    output_token: str
    input_amount: float
    
    # Execution details
    status: SwapStatus
    attempts: List[SwapAttempt] = field(default_factory=list)
    
    # Results
    final_transaction_id: Optional[str] = None
    actual_input_amount: Optional[float] = None
    actual_output_amount: Optional[float] = None
    price_impact: Optional[float] = None
    fee_collected: Optional[float] = None
    
    # Timing
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    # Error details
    final_error: Optional[str] = None
    error_classification: Optional[str] = None
    
    @property
    def is_successful(self) -> bool:
        """Check if swap was successful."""
        return self.status == SwapStatus.SUCCESS
    
    @property
    def total_duration(self) -> Optional[float]:
        """Calculate total operation duration."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None
    
    @property
    def attempt_count(self) -> int:
        """Get number of attempts made."""
        return len(self.attempts)


class SwapExecutor:
    """Executes individual wallet swaps with comprehensive error handling."""
    
    def __init__(self, api_client, execution_config: ExecutionConfig):
        """Initialize swap executor."""
        self.api_client = api_client
        self.config = execution_config
        self.quote_cache = {}  # Simple quote caching
        self.quote_cache_ttl = 30  # 30 seconds TTL
    
    async def execute_swap(
        self,
        wallet_address: str,
        wallet_private_key: str,
        wallet_index: int,
        input_token: str,
        output_token: str,
        amount: float
    ) -> SwapResult:
        """
        Execute a single wallet swap with retries and error handling.
        
        Args:
            wallet_address: Wallet public address
            wallet_private_key: Wallet private key
            wallet_index: Index of wallet in batch
            input_token: Input token symbol or mint
            output_token: Output token symbol or mint  
            amount: Amount to swap
        
        Returns:
            Detailed swap result
        """
        result = SwapResult(
            wallet_address=wallet_address,
            wallet_index=wallet_index,
            wallet_private_key=wallet_private_key,
            input_token=input_token,
            output_token=output_token,
            input_amount=amount,
            status=SwapStatus.PENDING,
            start_time=time.time()
        )
        
        logger.info(f"Starting swap for wallet {wallet_index}: {amount} {input_token} → {output_token}")
        
        # Pre-execution validation
        validation_error = await self._validate_swap_preconditions(result)
        if validation_error:
            result.status = SwapStatus.SKIPPED
            result.final_error = validation_error
            result.end_time = time.time()
            logger.warning(f"Swap validation failed for wallet {wallet_index}: {validation_error}")
            return result
        
        # Execute with retries
        max_attempts = self.config.max_retries + 1
        
        for attempt_num in range(1, max_attempts + 1):
            attempt = SwapAttempt(
                attempt_number=attempt_num,
                start_time=time.time()
            )
            result.attempts.append(attempt)
            
            try:
                success = await self._execute_swap_attempt(result, attempt)
                if success:
                    result.status = SwapStatus.SUCCESS
                    result.end_time = time.time()
                    logger.info(f"Swap successful for wallet {wallet_index} on attempt {attempt_num}")
                    break
                
            except Exception as e:
                attempt.status = SwapStatus.FAILED
                attempt.error = str(e)
                attempt.end_time = time.time()
                
                logger.warning(f"Swap attempt {attempt_num} failed for wallet {wallet_index}: {str(e)}")
                
                # Check if we should retry
                if attempt_num < max_attempts and self.config.retry_failed:
                    result.status = SwapStatus.RETRYING
                    await asyncio.sleep(self._calculate_retry_delay(attempt_num))
                else:
                    result.status = SwapStatus.FAILED
                    result.final_error = str(e)
                    result.error_classification = self._classify_error(str(e))
                    result.end_time = time.time()
                    break
        
        # Log final result
        if result.is_successful:
            logger.info(
                f"Swap completed for wallet {wallet_index}: "
                f"{result.actual_input_amount} {input_token} → {result.actual_output_amount} {output_token} "
                f"(TX: {result.final_transaction_id})"
            )
        else:
            logger.error(f"Swap failed for wallet {wallet_index} after {result.attempt_count} attempts: {result.final_error}")
        
        return result
    
    async def _validate_swap_preconditions(self, result: SwapResult) -> Optional[str]:
        """Validate conditions before attempting swap."""
        try:
            # Check minimum amount
            if result.input_amount <= 0:
                return f"Invalid amount: {result.input_amount}"
            
            # Check wallet balance (basic validation)
            if result.input_amount < 0.000001:  # Minimum reasonable amount
                return f"Amount too small: {result.input_amount}"
            
            # Additional validation can be added here
            return None
            
        except Exception as e:
            return f"Validation error: {str(e)}"
    
    async def _execute_swap_attempt(self, result: SwapResult, attempt: SwapAttempt) -> bool:
        """Execute a single swap attempt."""
        try:
            # Step 1: Get quote
            attempt.status = SwapStatus.QUOTE_REQUESTED
            quote_data = await self._get_fresh_quote(
                result.input_token,
                result.output_token,
                result.input_amount
            )
            
            if not quote_data:
                raise Exception("Failed to get valid quote")
            
            attempt.quote_data = quote_data
            attempt.status = SwapStatus.QUOTE_RECEIVED
            
            # Step 2: Execute swap
            attempt.status = SwapStatus.EXECUTING
            swap_response = await self._execute_jupiter_swap(
                result.wallet_private_key,
                quote_data
            )
            
            # Step 3: Process results
            if swap_response.get("status") == "success":
                attempt.status = SwapStatus.SUCCESS
                attempt.transaction_id = swap_response.get("transactionId")
                attempt.end_time = time.time()
                
                # Update result with successful swap data
                result.final_transaction_id = attempt.transaction_id
                result.actual_input_amount = self._extract_actual_input_amount(quote_data, swap_response)
                result.actual_output_amount = self._extract_actual_output_amount(quote_data, swap_response)
                result.price_impact = self._extract_price_impact(quote_data)
                result.fee_collected = self._extract_fee_amount(swap_response)
                
                return True
            else:
                raise Exception(f"Swap execution failed: {swap_response.get('message', 'Unknown error')}")
                
        except Exception as e:
            attempt.status = SwapStatus.FAILED
            attempt.error = str(e)
            attempt.end_time = time.time()
            raise
    
    async def _get_fresh_quote(
        self,
        input_token: str,
        output_token: str,
        amount: float
    ) -> Optional[Dict[str, Any]]:
        """Get a fresh quote from Jupiter, with caching."""
        cache_key = f"{input_token}_{output_token}_{amount}"
        current_time = time.time()
        
        # Check cache
        if cache_key in self.quote_cache:
            cached_quote, cache_time = self.quote_cache[cache_key]
            if current_time - cache_time < self.quote_cache_ttl:
                logger.debug(f"Using cached quote for {input_token} → {output_token}")
                return cached_quote
        
        try:
            # Convert amount to lamports/base units (assuming SOL input for now)
            amount_lamports = int(amount * 1_000_000_000) if input_token in ["SOL", "WSOL"] else int(amount)
            
            quote_response = self.api_client.get_jupiter_quote(
                input_mint=input_token,
                output_mint=output_token,
                amount=amount_lamports,
                slippage_bps=self.config.slippage_bps,
                only_direct_routes=False,
                as_legacy_transaction=False,
                platform_fee_bps=0
            )
            
            # Cache the quote
            self.quote_cache[cache_key] = (quote_response, current_time)
            
            logger.debug(f"Got fresh quote: {amount} {input_token} → {output_token}")
            return quote_response
            
        except Exception as e:
            logger.error(f"Failed to get quote: {str(e)}")
            return None
    
    async def _execute_jupiter_swap(
        self,
        private_key: str,
        quote_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute the actual Jupiter swap."""
        try:
            swap_response = self.api_client.execute_jupiter_swap(
                user_wallet_private_key=private_key,
                quote_response=quote_data,
                wrap_and_unwrap_sol=True,
                as_legacy_transaction=False,
                collect_fees=self.config.collect_fees,
                verify_swap=self.config.verify_swaps
            )
            
            return swap_response
            
        except Exception as e:
            logger.error(f"Jupiter swap execution failed: {str(e)}")
            raise
    
    def _extract_actual_input_amount(self, quote_data: Dict[str, Any], swap_response: Dict[str, Any]) -> Optional[float]:
        """Extract actual input amount from swap response."""
        try:
            quote_resp = quote_data.get("quoteResponse", {})
            in_amount = quote_resp.get("inAmount")
            if in_amount:
                # Convert from lamports to SOL (assuming SOL)
                return float(in_amount) / 1_000_000_000
        except:
            pass
        return None
    
    def _extract_actual_output_amount(self, quote_data: Dict[str, Any], swap_response: Dict[str, Any]) -> Optional[float]:
        """Extract actual output amount from swap response."""
        try:
            quote_resp = quote_data.get("quoteResponse", {})
            out_amount = quote_resp.get("outAmount")
            if out_amount:
                # Convert based on output token (simplified)
                return float(out_amount) / 1_000_000  # Assuming USDC (6 decimals)
        except:
            pass
        return None
    
    def _extract_price_impact(self, quote_data: Dict[str, Any]) -> Optional[float]:
        """Extract price impact from quote data."""
        try:
            quote_resp = quote_data.get("quoteResponse", {})
            price_impact = quote_resp.get("priceImpactPct")
            return float(price_impact) if price_impact else None
        except:
            return None
    
    def _extract_fee_amount(self, swap_response: Dict[str, Any]) -> Optional[float]:
        """Extract fee amount from swap response."""
        try:
            fee_collection = swap_response.get("feeCollection", {})
            if fee_collection and fee_collection.get("status") == "success":
                return fee_collection.get("feeAmount", 0.0)
        except:
            pass
        return None
    
    def _calculate_retry_delay(self, attempt_number: int) -> float:
        """Calculate delay before retry attempt."""
        # Exponential backoff with jitter
        base_delay = 1.0
        max_delay = 10.0
        delay = min(base_delay * (2 ** (attempt_number - 1)), max_delay)
        
        # Add random jitter to avoid thundering herd
        import random
        jitter = random.uniform(0.1, 0.3) * delay
        
        return delay + jitter
    
    def _classify_error(self, error_message: str) -> str:
        """Classify error type for better handling."""
        error_lower = error_message.lower()
        
        if "insufficient" in error_lower and "balance" in error_lower:
            return "insufficient_balance"
        elif "slippage" in error_lower or "price" in error_lower:
            return "slippage_exceeded"
        elif "timeout" in error_lower or "connection" in error_lower:
            return "network_error"
        elif "quote" in error_lower:
            return "quote_error"
        elif "transaction" in error_lower and "failed" in error_lower:
            return "transaction_failed"
        else:
            return "unknown_error"


class MockSwapExecutor(SwapExecutor):
    """Mock swap executor for testing without actual transactions."""
    
    def __init__(self, execution_config: ExecutionConfig):
        """Initialize mock executor without API client."""
        self.config = execution_config
        self.quote_cache = {}
        self.quote_cache_ttl = 30
        self.api_client = None  # No real API client needed
    
    async def _get_fresh_quote(self, input_token: str, output_token: str, amount: float) -> Optional[Dict[str, Any]]:
        """Generate mock quote data."""
        import random
        
        # Simulate quote retrieval delay
        await asyncio.sleep(random.uniform(0.1, 0.5))
        
        # Mock quote response
        amount_lamports = int(amount * 1_000_000_000) if input_token in ["SOL", "WSOL"] else int(amount)
        output_amount = int(amount_lamports * random.uniform(0.95, 1.05))  # ±5% variation
        
        return {
            "message": "Jupiter quote retrieved successfully",
            "quoteResponse": {
                "inputMint": input_token,
                "outputMint": output_token,
                "inAmount": str(amount_lamports),
                "outAmount": str(output_amount),
                "priceImpactPct": str(round(random.uniform(0.1, 3.0), 2)),
                "slippageBps": self.config.slippage_bps
            }
        }
    
    async def _execute_jupiter_swap(self, private_key: str, quote_data: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate swap execution."""
        import random
        
        # Simulate execution time
        await asyncio.sleep(random.uniform(2.0, 5.0))
        
        # Simulate occasional failures
        if random.random() < 0.1:  # 10% failure rate
            raise Exception("Mock transaction failed")
        
        # Mock successful response
        return {
            "status": "success",
            "transactionId": f"mock_tx_{int(time.time())}_{random.randint(1000, 9999)}",
            "feeCollection": {
                "status": "success",
                "feeAmount": 0.001,
                "transactionId": f"mock_fee_tx_{int(time.time())}"
            } if self.config.collect_fees else None,
            "message": "Mock swap executed successfully"
        } 