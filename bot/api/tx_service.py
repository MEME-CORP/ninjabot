"""
Transaction service for the Solana Volume Bot.

This module implements the transaction execution and retry logic
for Solana SPL token transfers.
"""

import time
import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable, Tuple

from bot.api.fee_service import FeeOracle

# Default confirmation timeout in seconds
DEFAULT_CONFIRMATION_TIMEOUT = 60

# Maximum number of retries for a transaction
MAX_RETRIES = 3

logger = logging.getLogger(__name__)

class TransactionError(Exception):
    """Base class for transaction-related errors."""
    pass

class GasSpikeError(TransactionError):
    """Error raised when a gas spike is detected."""
    def __init__(self, current_fee: int, threshold: float, avg_fee: int):
        self.current_fee = current_fee
        self.threshold = threshold
        self.avg_fee = avg_fee
        super().__init__(f"Gas spike detected: {current_fee} > {threshold} (avg: {avg_fee})")

class TransactionTimeoutError(TransactionError):
    """Error raised when a transaction confirmation times out."""
    pass

class TransactionExecutor:
    """
    Handles transaction execution, fee estimation, and retry logic
    for Solana transactions.
    """
    
    def __init__(
        self,
        fee_oracle: Optional[FeeOracle] = None,
        confirmation_timeout: int = DEFAULT_CONFIRMATION_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        user_approval_callback: Optional[Callable[[Dict[str, Any]], bool]] = None
    ):
        """
        Initialize the transaction executor.
        
        Args:
            fee_oracle: FeeOracle instance for fee recommendations
            confirmation_timeout: Timeout for transaction confirmations in seconds
            max_retries: Maximum number of retry attempts for failed transactions
            user_approval_callback: Optional callback for user approval of transactions
        """
        self.fee_oracle = fee_oracle or FeeOracle()
        self.confirmation_timeout = confirmation_timeout
        self.max_retries = max_retries
        self.user_approval_callback = user_approval_callback
    
    async def execute_spl_transfer(
        self,
        from_wallet_pubkey: str,
        to_wallet_pubkey: str,
        token_mint: str,
        amount: int,
        private_key: str,
        require_approval: bool = True
    ) -> Dict[str, Any]:
        """
        Execute an SPL token transfer on Solana.
        
        Args:
            from_wallet_pubkey: Sender's wallet public key
            to_wallet_pubkey: Recipient's wallet public key
            token_mint: Token mint address
            amount: Amount to transfer (in token's smallest unit)
            private_key: Private key for the sender wallet (for signing)
            require_approval: Whether to require user approval before execution
            
        Returns:
            Transaction result information
        """
        # Estimate fee for the transaction
        estimated_fee = self.fee_oracle.get_recommended_fee()
        
        # Check for gas spike
        if self.fee_oracle.is_gas_spike(estimated_fee):
            # In a real implementation, we'd get the actual average fee
            avg_fee = estimated_fee / self.fee_oracle.gas_spike_threshold
            
            # If user approval callback exists and requires approval
            if require_approval and self.user_approval_callback:
                approval_data = {
                    "from": from_wallet_pubkey,
                    "to": to_wallet_pubkey,
                    "amount": amount,
                    "token": token_mint,
                    "estimatedFee": estimated_fee,
                    "averageFee": int(avg_fee),
                    "spikeMultiplier": self.fee_oracle.gas_spike_threshold
                }
                
                # Wait for user approval
                approved = await self.user_approval_callback(approval_data)
                if not approved:
                    return {
                        "status": "ABORTED",
                        "reason": "User rejected gas spike",
                        "from": from_wallet_pubkey,
                        "to": to_wallet_pubkey,
                        "amount": amount,
                        "token": token_mint,
                        "estimatedFee": estimated_fee
                    }
            else:
                # No approval callback or not required, raise error
                raise GasSpikeError(
                    current_fee=estimated_fee,
                    threshold=avg_fee * self.fee_oracle.gas_spike_threshold,
                    avg_fee=int(avg_fee)
                )
        
        # Initialize retry counter
        retry_count = 0
        current_fee = estimated_fee
        
        # Keep trying until max retries reached
        while retry_count <= self.max_retries:
            try:
                # In a real implementation, this would:
                # 1. Create a Solana transaction using @solana/web3.js
                # 2. Sign it with the private key
                # 3. Send it to the Solana network
                # 4. Wait for confirmation with timeout
                
                # This is a placeholder that simulates the process
                logger.info(f"Executing SPL transfer: {from_wallet_pubkey} -> {to_wallet_pubkey}, amount: {amount}, retry: {retry_count}")
                
                # Simulate sending transaction
                # In reality, this would be a call to connection.sendTransaction()
                tx_hash = f"simulated_tx_hash_{int(time.time())}_{retry_count}"
                
                # Simulate waiting for confirmation
                # In reality, this would be a call to connection.confirmTransaction()
                await asyncio.sleep(min(2, self.confirmation_timeout / 10))  # Simulate confirmation time
                
                # Transaction successful
                return {
                    "status": "CONFIRMED",
                    "txHash": tx_hash,
                    "from": from_wallet_pubkey,
                    "to": to_wallet_pubkey,
                    "amount": amount,
                    "token": token_mint,
                    "fee": current_fee,
                    "retryCount": retry_count,
                    "confirmationTime": 2  # Simulated confirmation time in seconds
                }
                
            except Exception as e:
                # Increment retry counter
                retry_count += 1
                
                if retry_count > self.max_retries:
                    # Max retries reached, return failure
                    return {
                        "status": "FAILED",
                        "reason": str(e),
                        "from": from_wallet_pubkey,
                        "to": to_wallet_pubkey,
                        "amount": amount,
                        "token": token_mint,
                        "fee": current_fee,
                        "retryCount": retry_count - 1
                    }
                
                # Adjust fee for retry using binary backoff
                current_fee = self.fee_oracle.adjust_fee_for_retry(current_fee, retry_count)
                
                # Wait before retrying (exponential backoff)
                await asyncio.sleep(2 ** retry_count)  # 2, 4, 8 seconds
    
    async def execute_jupiter_swap(
        self,
        wallet_pubkey: str,
        token_in_mint: str,
        token_out_mint: str,
        amount_in: int,
        quote_response: Dict[str, Any],
        private_key: str,
        require_approval: bool = True
    ) -> Dict[str, Any]:
        """
        Execute a token swap via Jupiter.
        
        Args:
            wallet_pubkey: Wallet public key for the swap
            token_in_mint: Input token mint address
            token_out_mint: Output token mint address
            amount_in: Amount of input token (in smallest unit)
            quote_response: Jupiter quote response with swap instructions
            private_key: Private key for the wallet (for signing)
            require_approval: Whether to require user approval before execution
            
        Returns:
            Swap result information
        """
        # This is a placeholder for Jupiter swap implementation
        # In a real implementation, this would interact with Jupiter API
        
        # Simulate the swap process
        logger.info(f"Executing Jupiter swap: {token_in_mint} -> {token_out_mint}, amount: {amount_in}")
        
        # Simulate sending transaction
        tx_hash = f"simulated_jupiter_swap_{int(time.time())}"
        
        # Simulate waiting for confirmation
        await asyncio.sleep(min(3, self.confirmation_timeout / 10))  # Simulate confirmation time
        
        # Simulate output amount (in a real implementation, this would come from the swap result)
        amount_out = int(amount_in * 0.98)  # Simulate ~2% slippage
        
        return {
            "status": "CONFIRMED",
            "txHash": tx_hash,
            "wallet": wallet_pubkey,
            "tokenIn": token_in_mint,
            "tokenOut": token_out_mint,
            "amountIn": amount_in,
            "amountOut": amount_out,
            "slippage": f"{((amount_in - amount_out) / amount_in) * 100:.2f}%",
            "confirmationTime": 3  # Simulated confirmation time in seconds
        }

class ScheduledExecutor:
    """
    Executes a schedule of transactions according to their timestamps.
    """
    
    def __init__(
        self,
        tx_executor: Optional[TransactionExecutor] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """
        Initialize the scheduled executor.
        
        Args:
            tx_executor: TransactionExecutor instance
            progress_callback: Optional callback for execution progress updates
        """
        self.tx_executor = tx_executor or TransactionExecutor()
        self.progress_callback = progress_callback
        self.is_running = False
        self.should_stop = False
    
    async def execute_schedule(
        self,
        instructions: List[Dict[str, Any]],
        wallet_key_provider: Callable[[str], str]
    ) -> Dict[str, Any]:
        """
        Execute a schedule of transactions according to their timestamps.
        
        Args:
            instructions: List of transaction instructions with timestamps
            wallet_key_provider: Function that returns a private key for a wallet public key
            
        Returns:
            Execution results summary
        """
        if not instructions:
            return {"status": "FAILED", "reason": "No instructions provided"}
        
        # Sort instructions by execution timestamp
        sorted_instructions = sorted(instructions, key=lambda x: x["executeAtTimestamp"])
        
        # Track results
        results = []
        successful = 0
        failed = 0
        
        # Start execution
        self.is_running = True
        self.should_stop = False
        
        # Report start
        if self.progress_callback:
            self.progress_callback({
                "status": "STARTED",
                "totalInstructions": len(sorted_instructions),
                "timestamp": time.time()
            })
        
        # Execute each instruction at its scheduled time
        for i, instruction in enumerate(sorted_instructions):
            # Check if execution should stop
            if self.should_stop:
                if self.progress_callback:
                    self.progress_callback({
                        "status": "STOPPED",
                        "completed": i,
                        "totalInstructions": len(sorted_instructions),
                        "timestamp": time.time()
                    })
                break
            
            # Wait until the execution timestamp if it's in the future
            current_time = time.time()
            execution_time = instruction["executeAtTimestamp"]
            
            if execution_time > current_time:
                wait_time = execution_time - current_time
                
                # Report waiting status
                if self.progress_callback:
                    self.progress_callback({
                        "status": "WAITING",
                        "instruction": i + 1,
                        "totalInstructions": len(sorted_instructions),
                        "waitTime": wait_time,
                        "nextExecution": execution_time,
                        "timestamp": current_time
                    })
                
                # Wait until execution time
                await asyncio.sleep(wait_time)
            
            # Execute the instruction
            try:
                # Get private key for the wallet
                from_wallet = instruction["fromWalletPubkey"]
                private_key = wallet_key_provider(from_wallet)
                
                # Report execution start
                if self.progress_callback:
                    self.progress_callback({
                        "status": "EXECUTING",
                        "instruction": i + 1,
                        "totalInstructions": len(sorted_instructions),
                        "from": from_wallet,
                        "to": instruction["toWalletPubkey"],
                        "amount": instruction["amount"],
                        "timestamp": time.time()
                    })
                
                # Execute the transfer
                result = await self.tx_executor.execute_spl_transfer(
                    from_wallet_pubkey=from_wallet,
                    to_wallet_pubkey=instruction["toWalletPubkey"],
                    token_mint=instruction["tokenMint"],
                    amount=int(instruction["amount"]),
                    private_key=private_key
                )
                
                # Track result
                results.append(result)
                
                # Update counters
                if result["status"] == "CONFIRMED":
                    successful += 1
                else:
                    failed += 1
                
                # Report execution result
                if self.progress_callback:
                    self.progress_callback({
                        "status": "INSTRUCTION_COMPLETE",
                        "instruction": i + 1,
                        "totalInstructions": len(sorted_instructions),
                        "result": result,
                        "timestamp": time.time()
                    })
                
            except Exception as e:
                # Log error
                logger.error(f"Error executing instruction {i+1}: {str(e)}")
                
                # Track result
                failed += 1
                results.append({
                    "status": "FAILED",
                    "reason": str(e),
                    "from": instruction["fromWalletPubkey"],
                    "to": instruction["toWalletPubkey"],
                    "amount": instruction["amount"],
                    "tokenMint": instruction["tokenMint"]
                })
                
                # Report execution failure
                if self.progress_callback:
                    self.progress_callback({
                        "status": "INSTRUCTION_FAILED",
                        "instruction": i + 1,
                        "totalInstructions": len(sorted_instructions),
                        "error": str(e),
                        "timestamp": time.time()
                    })
        
        # Execution complete
        self.is_running = False
        
        # Report completion
        if self.progress_callback:
            self.progress_callback({
                "status": "COMPLETED",
                "successful": successful,
                "failed": failed,
                "total": len(sorted_instructions),
                "timestamp": time.time()
            })
        
        # Return summary
        return {
            "status": "COMPLETED",
            "successful": successful,
            "failed": failed,
            "total": len(sorted_instructions),
            "instructions": len(sorted_instructions),
            "results": results
        }
    
    def stop_execution(self):
        """Stop the current execution after the current instruction completes."""
        self.should_stop = True 