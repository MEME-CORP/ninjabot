"""
Enhanced API Verification Utilities

This module provides verification utilities to handle API behavioral inconsistencies
where immediate error responses don't reflect actual background processing outcomes.

Following MONOCODE principles:
- Observable Implementation: Structured logging for all verification steps
- Explicit Error Handling: Graceful fallbacks and comprehensive error context
- Progressive Construction: Incremental verification with fallback mechanisms
"""

import asyncio
import time
from typing import Dict, List, Any, Optional, Tuple
from loguru import logger

from bot.api.pumpfun_client import PumpFunApiError


class APIBehaviorHandler:
    """
    Handles API behavioral quirks where responses don't match actual processing outcomes.
    
    The PumpFun API exhibits asynchronous behavior:
    - May return errors immediately based on validation
    - Continues processing in background despite errors  
    - Actual results may differ from initial response
    """
    
    def __init__(self, pumpfun_client):
        self.pumpfun_client = pumpfun_client
        self.verification_timeout = 180  # 3 minutes for verification
        self.check_interval = 10  # Check every 10 seconds
        
    async def fund_with_verification(
        self, 
        funding_request: Dict[str, Any],
        expected_amount_per_wallet: float,
        wallet_count: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Fund wallets with built-in verification for API behavioral quirks.
        
        Args:
            funding_request: The funding request payload
            expected_amount_per_wallet: Expected SOL amount per wallet
            wallet_count: Number of wallets to fund
            
        Returns:
            Tuple of (success: bool, results: Dict)
        """
        start_time = time.time()
        operation_id = f"funding_{int(start_time)}"
        
        logger.info(
            f"🔧 API_VERIFICATION: Starting funding operation {operation_id}",
            extra={
                "operation_id": operation_id,
                "wallet_count": wallet_count,
                "amount_per_wallet": expected_amount_per_wallet
            }
        )
        
        # Step 1: Execute initial API call
        api_response = None
        api_error = None
        
        try:
            api_response = self.pumpfun_client.fund_bundled_wallets(
                funding_request["childWallets"],
                funding_request["amountPerWalletSOL"],
                funding_request["motherWalletPrivateKeyBs58"]
            )
            logger.info(f"🔧 API_VERIFICATION: Initial API call succeeded for {operation_id}")
            
        except Exception as e:
            api_error = e
            error_message = str(e)
            
            logger.warning(
                f"🔧 API_VERIFICATION: Initial API call failed for {operation_id}: {error_message}",
                extra={"operation_id": operation_id, "error_type": type(e).__name__}
            )
            
            # Check if this is a known async processing error
            if self._is_async_processing_error(error_message):
                logger.info(f"🔧 API_VERIFICATION: Detected async processing error - will verify actual results")
            else:
                # This is likely a genuine error, but still verify to be sure
                logger.info(f"🔧 API_VERIFICATION: Unknown error type - will still verify actual results")
        
        # Step 2: Always verify actual wallet states regardless of API response
        logger.info(f"🔧 API_VERIFICATION: Starting wallet state verification for {operation_id}")
        
        verification_result = await self._verify_funding_completion(
            funding_request["childWallets"],
            expected_amount_per_wallet,
            operation_id
        )
        
        execution_time = time.time() - start_time
        
        # Step 3: Generate comprehensive results
        results = {
            "operation_id": operation_id,
            "execution_time": execution_time,
            "initial_api_success": api_error is None,
            "initial_api_error": str(api_error) if api_error else None,
            "verification_results": verification_result,
            "total_wallets": wallet_count,
            "funded_wallets": verification_result["funded_count"],
            "unfunded_wallets": verification_result["unfunded_count"],
            "success_rate": verification_result["success_rate"]
        }
        
        overall_success = verification_result["funded_count"] > 0
        
        logger.info(
            f"🔧 API_VERIFICATION: Operation {operation_id} complete",
            extra={
                "operation_id": operation_id,
                "overall_success": overall_success,
                "funded_wallets": results["funded_wallets"],
                "unfunded_wallets": results["unfunded_wallets"],
                "success_rate": results["success_rate"],
                "execution_time": execution_time
            }
        )
        
        return overall_success, results
    
    async def _verify_funding_completion(
        self,
        child_wallets: List[Dict[str, str]],
        expected_amount: float,
        operation_id: str
    ) -> Dict[str, Any]:
        """
        Verify actual funding completion by checking wallet balances.
        
        Args:
            child_wallets: List of wallet dictionaries with names and keys
            expected_amount: Expected SOL amount per wallet
            operation_id: Unique operation identifier
            
        Returns:
            Dictionary with verification results
        """
        # Calculate minimum acceptable balance (80% of expected to account for fees)
        minimum_balance = expected_amount * 0.8
        
        logger.info(
            f"🔧 VERIFICATION: Starting balance verification for {len(child_wallets)} wallets",
            extra={
                "operation_id": operation_id,
                "expected_amount": expected_amount,
                "minimum_balance": minimum_balance
            }
        )
        
        # Wait initial period for API processing
        initial_wait = min(30, len(child_wallets) * 2)  # 2 seconds per wallet, max 30 seconds
        logger.info(f"🔧 VERIFICATION: Waiting {initial_wait}s for API processing to begin")
        await asyncio.sleep(initial_wait)
        
        funded_wallets = []
        unfunded_wallets = []
        verification_start = time.time()
        
        # Progressive verification with timeout
        while time.time() - verification_start < self.verification_timeout:
            current_funded = []
            current_unfunded = []
            
            for wallet in child_wallets:
                wallet_name = wallet.get("name", "Unknown")
                
                try:
                    # Get wallet address from private key
                    wallet_address = self._get_wallet_address(wallet)
                    
                    if not wallet_address:
                        logger.warning(f"Could not derive address for wallet {wallet_name}")
                        current_unfunded.append({
                            "name": wallet_name,
                            "error": "Could not derive wallet address",
                            "balance": 0.0
                        })
                        continue
                    
                    # Check balance
                    balance = await self._check_wallet_balance(wallet_address, wallet_name)
                    
                    if balance >= minimum_balance:
                        current_funded.append({
                            "name": wallet_name,
                            "address": wallet_address,
                            "balance": balance
                        })
                        logger.info(f"🔧 VERIFICATION: ✅ {wallet_name} funded: {balance:.6f} SOL")
                    else:
                        current_unfunded.append({
                            "name": wallet_name,
                            "address": wallet_address,
                            "balance": balance
                        })
                        
                except Exception as e:
                    logger.warning(f"🔧 VERIFICATION: Error checking {wallet_name}: {str(e)}")
                    current_unfunded.append({
                        "name": wallet_name,
                        "error": str(e),
                        "balance": 0.0
                    })
            
            funded_wallets = current_funded
            unfunded_wallets = current_unfunded
            
            # Log progress
            funded_count = len(funded_wallets)
            total_wallets = len(child_wallets)
            success_rate = (funded_count / total_wallets * 100) if total_wallets > 0 else 0
            
            logger.info(
                f"🔧 VERIFICATION: Progress - {funded_count}/{total_wallets} wallets funded ({success_rate:.1f}%)",
                extra={
                    "operation_id": operation_id,
                    "funded_count": funded_count,
                    "total_wallets": total_wallets,
                    "success_rate": success_rate
                }
            )
            
            # Check if we should continue waiting
            if funded_count == 0:
                # No wallets funded yet, continue waiting
                await asyncio.sleep(self.check_interval)
                continue
            elif funded_count == total_wallets:
                # All wallets funded, we're done
                logger.info(f"🔧 VERIFICATION: All wallets funded successfully")
                break
            else:
                # Partial funding - wait a bit more to see if more complete
                remaining_time = self.verification_timeout - (time.time() - verification_start)
                if remaining_time > 30:  # If more than 30 seconds left, wait a bit more
                    await asyncio.sleep(self.check_interval)
                    continue
                else:
                    # Time is running out, accept partial results
                    logger.info(f"🔧 VERIFICATION: Accepting partial funding results due to timeout")
                    break
        
        verification_time = time.time() - verification_start
        
        results = {
            "funded_wallets": funded_wallets,
            "unfunded_wallets": unfunded_wallets,
            "funded_count": len(funded_wallets),
            "unfunded_count": len(unfunded_wallets),
            "total_count": len(child_wallets),
            "success_rate": (len(funded_wallets) / len(child_wallets) * 100) if child_wallets else 0,
            "verification_time": verification_time,
            "minimum_balance_threshold": minimum_balance
        }
        
        logger.info(
            f"🔧 VERIFICATION: Completed verification in {verification_time:.1f}s",
            extra={
                "operation_id": operation_id,
                "results": results
            }
        )
        
        return results
    
    def _is_async_processing_error(self, error_message: str) -> bool:
        """
        Check if an error message indicates async processing behavior.
        
        Args:
            error_message: The error message to analyze
            
        Returns:
            True if this appears to be an async processing error
        """
        async_indicators = [
            "insufficient SOL",
            "insufficient balance",
            "not enough funds",
            "balance too low"
        ]
        
        return any(indicator.lower() in error_message.lower() for indicator in async_indicators)
    
    def _get_wallet_address(self, wallet: Dict[str, str]) -> Optional[str]:
        """
        Get wallet address from wallet data.
        
        Args:
            wallet: Wallet dictionary
            
        Returns:
            Wallet address if available
        """
        # Try different possible keys for address
        address_keys = ["address", "publicKey", "public_key", "wallet_address"]
        
        for key in address_keys:
            if key in wallet and wallet[key]:
                return wallet[key]
        
        # If no address found, try to derive from private key
        # This would require additional crypto utilities
        return None
    
    async def _check_wallet_balance(self, wallet_address: str, wallet_name: str) -> float:
        """
        Check individual wallet balance with error handling.
        
        Args:
            wallet_address: The wallet address to check
            wallet_name: The wallet name for logging
            
        Returns:
            Wallet balance in SOL, 0.0 if error
        """
        try:
            balance_response = self.pumpfun_client.get_wallet_balance(wallet_address)
            
            # Handle different response formats
            if isinstance(balance_response, dict):
                if "data" in balance_response and "balance" in balance_response["data"]:
                    return float(balance_response["data"]["balance"])
                elif "balance" in balance_response:
                    return float(balance_response["balance"])
            elif isinstance(balance_response, (int, float)):
                return float(balance_response)
            
            logger.warning(f"Unexpected balance response format for {wallet_name}: {balance_response}")
            return 0.0
            
        except Exception as e:
            logger.warning(f"Error checking balance for {wallet_name}: {str(e)}")
            return 0.0


def create_funding_verification_system(pumpfun_client) -> APIBehaviorHandler:
    """
    Factory function to create API behavior handler with proper configuration.
    
    Args:
        pumpfun_client: The PumpFun API client instance
        
    Returns:
        Configured APIBehaviorHandler instance
    """
    return APIBehaviorHandler(pumpfun_client)
