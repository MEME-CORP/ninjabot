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
        self.verification_timeout = 420  # 7 minutes base verification timeout
        self.check_interval = 10  # Check every 10 seconds
        # Long-tail extension window to keep waiting if progress is still occurring
        self.long_tail_extension = 120  # up to +2 minutes if progress observed
        # Absolute ceiling to avoid indefinite waits even with progress
        self.max_total_timeout = 600  # 10 minutes hard cap
        
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
                amount_per_wallet=funding_request["amountPerWalletSOL"],
                mother_private_key=funding_request["motherWalletPrivateKeyBs58"],
                bundled_wallets=funding_request["childWallets"],
                target_wallet_names=funding_request.get("targetWalletNames")
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
        
        api_hints = None
        try:
            # Extract non-sensitive hints from API response (e.g., bundleId, transfer statuses)
            api_hints = self._extract_api_hints(api_response) if api_response is not None else None
        except Exception as e:
            logger.debug(f"🔧 API_VERIFICATION: Failed to extract API hints: {e}")

        verification_result = await self._verify_funding_completion(
            funding_request["childWallets"],
            expected_amount_per_wallet,
            operation_id,
            addresses_by_name=funding_request.get("addressesByName"),
            api_hints=api_hints,
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
        operation_id: str,
        addresses_by_name: Optional[Dict[str, str]] = None,
        api_hints: Optional[Dict[str, Any]] = None,
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
        last_progress_time = verification_start
        prev_max_funded = 0
        
        # Progressive verification with timeout + long-tail extension on progress
        while True:
            current_funded = []
            current_unfunded = []
            
            for wallet in child_wallets:
                wallet_name = wallet.get("name", "Unknown")
                
                try:
                    # Get wallet address from private key
                    wallet_address = self._get_wallet_address(wallet)
                    if not wallet_address and addresses_by_name:
                        wallet_address = addresses_by_name.get(wallet_name)
                    
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

            # Update progress timestamp if we observed more funded wallets this iteration
            if funded_count > prev_max_funded:
                prev_max_funded = funded_count
                last_progress_time = time.time()

            # Determine whether the API indicated in-progress work for any unfunded wallet
            observed_activity = False
            if api_hints and isinstance(api_hints, dict):
                status_by_wallet = api_hints.get("transfer_status_by_wallet", {}) or {}
                for item in unfunded_wallets:
                    wname = item.get("name")
                    wstatus = status_by_wallet.get(wname)
                    if isinstance(wstatus, str) and wstatus.lower() in {"processing", "queued", "submitted", "pending"}:
                        observed_activity = True
                        break

            # Check if we should continue waiting
            if funded_count == 0:
                # No wallets funded yet, continue waiting
                await asyncio.sleep(self.check_interval)
                # Continue if still within base timeout, else only continue if activity observed and within long-tail
                elapsed = time.time() - verification_start
                if elapsed < self.verification_timeout:
                    continue
                if (elapsed < self.max_total_timeout) and (time.time() - last_progress_time < self.long_tail_extension or observed_activity):
                    logger.info("🔧 VERIFICATION: Extending wait (no initial funding yet, activity observed or within long-tail window)")
                    await asyncio.sleep(self.check_interval)
                    continue
                logger.info("🔧 VERIFICATION: Timeout reached with no funding observed")
                break
            elif funded_count == total_wallets:
                # All wallets funded, we're done
                logger.info(f"🔧 VERIFICATION: All wallets funded successfully")
                break
            else:
                # Partial funding - wait a bit more to see if more complete
                elapsed = time.time() - verification_start
                if elapsed < self.verification_timeout:
                    await asyncio.sleep(self.check_interval)
                    continue
                # Base timeout exceeded: allow a long-tail extension if we recently saw progress or API hinted activity
                if (elapsed < self.max_total_timeout) and (time.time() - last_progress_time < self.long_tail_extension or observed_activity):
                    logger.info("🔧 VERIFICATION: Extending wait (partial funding with recent progress or API activity)")
                    await asyncio.sleep(self.check_interval)
                    continue
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
    
    def _extract_api_hints(self, api_response: Any) -> Dict[str, Any]:
        """
        Extract non-sensitive hints from the initial API response to guide verification.
        This does not replace balance checks, but can inform extended waiting when activity is observed.

        Attempts to parse commonly seen fields like 'data.transfers' or 'transfers' to map wallet names
        to statuses if available, and capture a 'bundleId' if present.

        Args:
            api_response: Raw API response from fund_bundled_wallets()

        Returns:
            Dict with optional keys like 'bundleId' and 'transfer_status_by_wallet'.
        """
        hints: Dict[str, Any] = {}
        if not isinstance(api_response, dict):
            return hints
        data = api_response.get("data") if isinstance(api_response.get("data"), (dict, list)) else None

        # Bundle ID if present
        if isinstance(data, dict) and "bundleId" in data:
            hints["bundleId"] = data.get("bundleId")

        # Transfers may be a list at api_response['data']['transfers'] or top-level 'transfers'
        transfers = None
        if isinstance(data, dict) and isinstance(data.get("transfers"), list):
            transfers = data.get("transfers")
        elif isinstance(api_response.get("transfers"), list):
            transfers = api_response.get("transfers")

        status_by_wallet: Dict[str, str] = {}
        if isinstance(transfers, list):
            for t in transfers:
                if not isinstance(t, dict):
                    continue
                # Try to map by wallet name if present, otherwise skip
                wname = t.get("name") or t.get("walletName")
                wstatus = t.get("status") or t.get("state")
                if isinstance(wname, str) and isinstance(wstatus, str):
                    status_by_wallet[wname] = wstatus
        if status_by_wallet:
            hints["transfer_status_by_wallet"] = status_by_wallet

        return hints

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
    
    async def return_with_verification(
        self, 
        mother_wallet_public_key: str,
        child_wallets: List[Dict[str, str]]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Return funds to mother wallet with built-in verification for API behavioral quirks.
        
        This method mirrors the funding verification logic but checks for wallet balance 
        reductions instead of increases to verify successful fund returns.
        
        Args:
            mother_wallet_public_key: The mother wallet public key
            child_wallets: List of child wallet credentials
            
        Returns:
            Tuple of (success: bool, results: Dict)
        """
        start_time = time.time()
        operation_id = f"return_funds_{int(start_time)}"
        
        logger.info(
            f"🔧 API_VERIFICATION: Starting return funds operation {operation_id}",
            extra={
                "operation_id": operation_id,
                "wallet_count": len(child_wallets)
            }
        )
        
        # Step 1: Record initial wallet balances to detect changes
        logger.info(f"🔧 API_VERIFICATION: Recording initial wallet balances for {operation_id}")
        initial_balances = {}
        
        for wallet in child_wallets:
            wallet_name = wallet.get("name", "Unknown")
            
            # Use wallet address from wallet data (like funding verification does)
            try:
                wallet_address = self._get_wallet_address(wallet)
                if not wallet_address:
                    logger.warning(f"Could not find address for wallet {wallet_name}")
                    continue
                    
                balance = await self._check_wallet_balance(wallet_address, wallet_name)
                initial_balances[wallet_name] = {
                    "address": wallet_address,
                    "balance": balance
                }
                logger.info(f"🔧 VERIFICATION: Initial {wallet_name} balance: {balance:.6f} SOL")
            except Exception as e:
                logger.warning(f"🔧 VERIFICATION: Error recording initial balance for {wallet_name}: {str(e)}")
                continue
        
        # Step 2: Execute initial API call
        api_response = None
        api_error = None
        
        try:
            api_response = self.pumpfun_client.return_funds_to_mother(
                mother_wallet_public_key=mother_wallet_public_key,
                child_wallets=child_wallets
            )
            logger.info(f"🔧 API_VERIFICATION: Initial API call succeeded for {operation_id}")
            
        except Exception as e:
            api_error = e
            error_message = str(e)
            
            logger.warning(
                f"🔧 API_VERIFICATION: Initial API call failed for {operation_id}: {error_message}",
                extra={"operation_id": operation_id, "error_type": type(e).__name__}
            )
        
        # Step 3: Always verify actual wallet states regardless of API response
        logger.info(f"🔧 API_VERIFICATION: Starting wallet state verification for {operation_id}")
        
        # Extract hints from API response for better verification guidance
        api_hints = self._extract_api_hints(api_response) if api_response else {}
        
        # Perform verification with enhanced logic
        verification_results = await self._verify_return_completion(
            initial_balances,
            child_wallets,
            operation_id,
            api_hints
        )
        
        # Step 4: Determine overall success
        returned_wallets = verification_results["returned_wallets"]
        not_returned_wallets = verification_results["not_returned_wallets"]
        
        total_returned = len(returned_wallets)
        total_expected = len(initial_balances)
        success_rate = (total_returned / total_expected * 100) if total_expected > 0 else 0
        
        # Consider operation successful if most wallets returned funds
        overall_success = success_rate >= 80.0  # 80% threshold like funding verification
        
        operation_time = time.time() - start_time
        
        final_results = {
            "success": overall_success,
            "returned_wallets": returned_wallets,
            "not_returned_wallets": not_returned_wallets,
            "returned_count": total_returned,
            "not_returned_count": len(not_returned_wallets),
            "total_count": total_expected,
            "success_rate": success_rate,
            "operation_time": operation_time,
            "api_response": api_response,
            "api_error": str(api_error) if api_error else None,
            "verification_results": verification_results
        }
        
        logger.info(
            f"🔧 API_VERIFICATION: Return funds operation {operation_id} completed - "
            f"Success: {overall_success}, Rate: {success_rate:.1f}%",
            extra={
                "operation_id": operation_id,
                "results": final_results
            }
        )
        
        return overall_success, final_results
    
    async def _verify_return_completion(
        self,
        initial_balances: Dict[str, Dict[str, Any]],
        child_wallets: List[Dict[str, str]],
        operation_id: str,
        api_hints: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Verify return funds completion by checking wallet balance reductions.
        
        Args:
            initial_balances: Dictionary of initial wallet balances
            child_wallets: List of child wallet credentials
            operation_id: Operation identifier for logging
            api_hints: Hints from API response
            
        Returns:
            Dictionary with verification results
        """
        verification_start = time.time()
        returned_wallets = []
        not_returned_wallets = []
        
        # Threshold for considering funds "returned" - balance should be significantly reduced
        min_reduction_threshold = 0.02  # At least 0.02 SOL reduction to be considered "returned"
        
        # Progress tracking
        prev_max_returned = 0
        last_progress_time = verification_start
        
        while time.time() - verification_start < self.max_total_timeout:
            current_returned = []
            current_not_returned = []
            
            # Check each wallet's current balance vs initial balance
            for wallet_name, initial_data in initial_balances.items():
                try:
                    wallet_address = initial_data["address"]
                    initial_balance = initial_data["balance"]
                    
                    # Check current balance
                    current_balance = await self._check_wallet_balance(wallet_address, wallet_name)
                    balance_reduction = initial_balance - current_balance
                    
                    if balance_reduction >= min_reduction_threshold:
                        current_returned.append({
                            "name": wallet_name,
                            "address": wallet_address,
                            "initial_balance": initial_balance,
                            "final_balance": current_balance,
                            "amount_returned": balance_reduction
                        })
                        logger.info(f"🔧 VERIFICATION: ✅ {wallet_name} returned: {balance_reduction:.6f} SOL")
                    else:
                        current_not_returned.append({
                            "name": wallet_name,
                            "address": wallet_address,
                            "initial_balance": initial_balance,
                            "final_balance": current_balance,
                            "amount_returned": balance_reduction
                        })
                        
                except Exception as e:
                    logger.warning(f"🔧 VERIFICATION: Error checking {wallet_name}: {str(e)}")
                    current_not_returned.append({
                        "name": wallet_name,
                        "error": str(e),
                        "initial_balance": initial_balances.get(wallet_name, {}).get("balance", 0.0),
                        "final_balance": 0.0,
                        "amount_returned": 0.0
                    })
            
            returned_wallets = current_returned
            not_returned_wallets = current_not_returned
            
            # Log progress
            returned_count = len(returned_wallets)
            total_wallets = len(initial_balances)
            success_rate = (returned_count / total_wallets * 100) if total_wallets > 0 else 0
            
            logger.info(
                f"🔧 VERIFICATION: Progress - {returned_count}/{total_wallets} wallets returned funds ({success_rate:.1f}%)",
                extra={
                    "operation_id": operation_id,
                    "returned_count": returned_count,
                    "total_wallets": total_wallets,
                    "success_rate": success_rate
                }
            )

            # Update progress timestamp if we observed more returned wallets this iteration
            if returned_count > prev_max_returned:
                prev_max_returned = returned_count
                last_progress_time = time.time()

            # Determine whether the API indicated in-progress work
            observed_activity = False
            if api_hints and isinstance(api_hints, dict):
                status_by_wallet = api_hints.get("transfer_status_by_wallet", {}) or {}
                for item in not_returned_wallets:
                    wname = item.get("name")
                    wstatus = status_by_wallet.get(wname)
                    if isinstance(wstatus, str) and wstatus.lower() in {"processing", "queued", "submitted", "pending"}:
                        observed_activity = True
                        break

            # Check if we should continue waiting
            if returned_count == 0:
                # No wallets returned yet, continue waiting
                await asyncio.sleep(self.check_interval)
                # Continue if still within base timeout, else only continue if activity observed and within long-tail
                elapsed = time.time() - verification_start
                if elapsed < self.verification_timeout:
                    continue
                if (elapsed < self.max_total_timeout) and (time.time() - last_progress_time < self.long_tail_extension or observed_activity):
                    logger.info("🔧 VERIFICATION: Extending wait (no returns yet, activity observed or within long-tail window)")
                    await asyncio.sleep(self.check_interval)
                    continue
                logger.info("🔧 VERIFICATION: Timeout reached with no returns observed")
                break
            elif returned_count == total_wallets:
                # All wallets returned funds, we're done
                logger.info(f"🔧 VERIFICATION: All wallets returned funds successfully")
                break
            else:
                # Partial returns - wait a bit more to see if more complete
                elapsed = time.time() - verification_start
                if elapsed < self.verification_timeout:
                    await asyncio.sleep(self.check_interval)
                    continue
                # Base timeout exceeded: allow a long-tail extension if we recently saw progress or API hinted activity
                if (elapsed < self.max_total_timeout) and (time.time() - last_progress_time < self.long_tail_extension or observed_activity):
                    logger.info("🔧 VERIFICATION: Extending wait (partial returns with recent progress or API activity)")
                    await asyncio.sleep(self.check_interval)
                    continue
                # Time is running out, accept partial results
                logger.info(f"🔧 VERIFICATION: Accepting partial return results due to timeout")
                break
        
        verification_time = time.time() - verification_start
        
        results = {
            "returned_wallets": returned_wallets,
            "not_returned_wallets": not_returned_wallets,
            "returned_count": len(returned_wallets),
            "not_returned_count": len(not_returned_wallets),
            "total_count": len(initial_balances),
            "success_rate": (len(returned_wallets) / len(initial_balances) * 100) if initial_balances else 0,
            "verification_time": verification_time,
            "min_reduction_threshold": min_reduction_threshold
        }
        
        logger.info(
            f"🔧 VERIFICATION: Completed return verification in {verification_time:.1f}s",
            extra={
                "operation_id": operation_id,
                "results": results
            }
        )
        
        return results
    



def create_funding_verification_system(pumpfun_client) -> APIBehaviorHandler:
    """
    Factory function to create API behavior handler with proper configuration.
    
    Args:
        pumpfun_client: The PumpFun API client instance
        
    Returns:
        Configured APIBehaviorHandler instance
    """
    return APIBehaviorHandler(pumpfun_client)
