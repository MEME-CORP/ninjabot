"""
Transaction execution for Solana.
"""

import time
import base58
from typing import Dict, List, Any, Optional, Callable, Awaitable
import asyncio
from datetime import datetime, timedelta
from loguru import logger

from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solana.rpc.async_api import AsyncClient
from solana.transaction import Transaction
from solders.system_program import TransferParams, transfer
from solders.keypair import Keypair
from solders.pubkey import Pubkey

from bot.solana.models import TransferOp, Schedule, FeeEstimate
from bot.solana.fee_oracle import FeeOracle
from bot.solana.wallet_manager import WalletManager
from bot.solana.token_program import (
    get_token_account, 
    execute_token_transfer, 
    wait_for_token_transfer_confirmation
)

class TxExecutor:
    """
    Executes Solana transactions with retry logic and error handling.
    """
    
    # Maximum number of retry attempts
    MAX_RETRIES = 3
    # Retry backoff in seconds
    RETRY_BACKOFF = 2
    # Confirmation timeout in seconds
    CONFIRMATION_TIMEOUT = 30
    
    def __init__(self, 
                wallet_manager: WalletManager, 
                fee_oracle: FeeOracle,
                network="devnet",
                on_tx_sent=None,
                on_tx_confirmed=None,
                on_tx_failed=None,
                on_tx_retry=None):
        """
        Initialize the transaction executor.
        
        Args:
            wallet_manager: WalletManager instance
            fee_oracle: FeeOracle instance
            network: Solana network (devnet or mainnet)
            on_tx_sent: Callback when transaction is sent
            on_tx_confirmed: Callback when transaction is confirmed
            on_tx_failed: Callback when transaction fails
            on_tx_retry: Callback when transaction is retried
        """
        self.wallet_manager = wallet_manager
        self.fee_oracle = fee_oracle
        self.network = network
        self.rpc_url = "https://api.devnet.solana.com" if network == "devnet" else "https://api.mainnet-beta.solana.com"
        self.client = Client(self.rpc_url)
        self.async_client = AsyncClient(self.rpc_url)
        
        # Cache for token accounts to reduce RPC calls
        self._token_account_cache = {}
        
        # Event callbacks
        self.on_tx_sent = on_tx_sent
        self.on_tx_confirmed = on_tx_confirmed
        self.on_tx_failed = on_tx_failed
        self.on_tx_retry = on_tx_retry
        
        logger.info(f"TxExecutor initialized on {network}")
    
    async def run(self, schedule: Schedule, wallet_keypairs: Dict[str, str]):
        """
        Executes a schedule of transfers with error handling and retries.
        
        Args:
            schedule: Schedule of transfers to execute
            wallet_keypairs: Dictionary mapping wallet addresses to encrypted secret keys
            
        Returns:
            Updated schedule with execution results
        """
        logger.info(f"Starting execution of schedule {schedule.id}")
        
        # Update schedule status
        schedule.status = "in_progress"
        
        # Sort transfers by estimated time
        transfers = sorted(schedule.transfers, key=lambda t: t.estimated_time)
        
        # Execute transfers
        for transfer_op in transfers:
            # Check if it's time to execute this transfer
            now = datetime.now()
            if transfer_op.estimated_time > now:
                # Sleep until it's time to execute
                sleep_time = (transfer_op.estimated_time - now).total_seconds()
                logger.info(f"Waiting {sleep_time:.2f} seconds until next transfer")
                await asyncio.sleep(sleep_time)
            
            # Execute the transfer
            try:
                # Get sender keypair
                sender_secret = wallet_keypairs.get(transfer_op.from_address)
                if not sender_secret:
                    logger.error(f"No keypair found for sender {transfer_op.from_address}")
                    transfer_op.status = "failed"
                    transfer_op.error_message = "No keypair found for sender"
                    continue
                
                # Execute the transfer
                result = await self.execute_transfer(transfer_op, sender_secret)
                
                # Update transfer with result
                transfer_op.status = "completed" if result.get("success") else "failed"
                transfer_op.tx_hash = result.get("tx_hash")
                transfer_op.execution_time = datetime.now()
                transfer_op.error_message = result.get("error")
                
                # If failed, log the error
                if not result.get("success"):
                    logger.error(
                        f"Transfer failed: {result.get('error')}",
                        extra={"transfer": transfer_op.dict(), "error": result.get("error")}
                    )
                
            except Exception as e:
                logger.exception(f"Error executing transfer: {str(e)}")
                transfer_op.status = "failed"
                transfer_op.execution_time = datetime.now()
                transfer_op.error_message = str(e)
        
        # Update schedule status
        if all(t.status == "completed" for t in schedule.transfers):
            schedule.status = "completed"
        elif any(t.status == "failed" for t in schedule.transfers):
            schedule.status = "failed"
        
        schedule.completed_at = datetime.now()
        
        logger.info(
            f"Schedule execution completed with status: {schedule.status}",
            extra={"schedule_id": schedule.id, "status": schedule.status}
        )
        
        return schedule
    
    async def execute_transfer(self, transfer: TransferOp, sender_secret: str) -> Dict[str, Any]:
        """
        Executes a single transfer with retry logic.
        
        Args:
            transfer: Transfer operation to execute
            sender_secret: Encrypted sender secret key
            
        Returns:
            Result dictionary with success status and transaction hash
        """
        logger.info(
            f"Executing transfer from {transfer.from_address} to {transfer.to_address}",
            extra={"amount": transfer.amount, "token_mint": transfer.token_mint}
        )
        
        # Get fee estimate
        fee_estimate = self.fee_oracle.get_current_fee_estimate()
        
        # If fee spike detected, wait a bit and check again
        if fee_estimate.is_spike:
            logger.warning(f"Fee spike detected ({fee_estimate.lamports} lamports), waiting 30 seconds")
            await asyncio.sleep(30)
            fee_estimate = self.fee_oracle.get_current_fee_estimate()
        
        # Save fee estimate for this transfer
        transfer.fee_lamports = fee_estimate.lamports
        
        # Update status
        transfer.status = "in_progress"
        transfer.execution_time = datetime.now()
        
        # Try to execute with retries
        result = {"success": False, "tx_hash": None, "error": None}
        retry_count = 0
        
        while retry_count <= self.MAX_RETRIES:
            try:
                # Get sender keypair
                keypair = self.wallet_manager.get_keypair(sender_secret)
                
                # Get recent blockhash
                blockhash = self.fee_oracle.get_blockhash()
                if not blockhash:
                    raise Exception("Failed to get recent blockhash")
                
                # Check if this is a native SOL transfer or an SPL token transfer
                if transfer.token_mint == "11111111111111111111111111111111":
                    # Native SOL transfer
                    result = await self._execute_sol_transfer(
                        keypair=keypair,
                        recipient=transfer.to_address,
                        amount=transfer.amount,
                        blockhash=blockhash
                    )
                else:
                    # SPL token transfer
                    result = await self._execute_token_transfer(
                        keypair=keypair,
                        recipient=transfer.to_address,
                        token_mint=transfer.token_mint,
                        amount=transfer.amount,
                        blockhash=blockhash
                    )
                
                # Update retry count
                transfer.retry_count = retry_count
                
                # Handle callbacks based on result
                if result["success"]:
                    # Invoke sent callback
                    if self.on_tx_sent:
                        self.on_tx_sent({
                            "transfer": transfer.dict(),
                            "tx_hash": result["tx_hash"],
                            "timestamp": datetime.now().isoformat()
                        })
                    
                    # Invoke confirmed callback if transaction was successful
                    if self.on_tx_confirmed:
                        self.on_tx_confirmed({
                            "transfer": transfer.dict(),
                            "tx_hash": result["tx_hash"],
                            "timestamp": datetime.now().isoformat()
                        })
                    
                    # Clear keypair from memory
                    self.wallet_manager.clear_keypair_from_memory(keypair)
                    break
                else:
                    # Check for specific error conditions that might warrant aborting retries
                    error = result.get("error", "")
                    if "InsufficientFundsForFee" in error or "InsufficientFundsForRent" in error:
                        logger.warning(f"Insufficient funds, aborting retries: {error}")
                        
                        # Clear keypair from memory
                        self.wallet_manager.clear_keypair_from_memory(keypair)
                        break
            
            except Exception as e:
                logger.exception(f"Error executing transfer: {str(e)}")
                result = {"success": False, "tx_hash": None, "error": str(e)}
            
            # Increment retry count
            retry_count += 1
            
            # If we still have retries left, wait and retry
            if retry_count <= self.MAX_RETRIES and not result["success"]:
                backoff = self.RETRY_BACKOFF * (2 ** (retry_count - 1))
                logger.warning(
                    f"Retrying transfer in {backoff} seconds (attempt {retry_count}/{self.MAX_RETRIES})",
                    extra={"retry_count": retry_count, "backoff": backoff}
                )
                
                # Update transfer retry count
                transfer.retry_count = retry_count
                
                # Invoke retry callback
                if self.on_tx_retry:
                    self.on_tx_retry({
                        "transfer": transfer.dict(),
                        "retry_count": retry_count,
                        "error": result["error"],
                        "timestamp": datetime.now().isoformat()
                    })
                
                # Wait before retrying
                await asyncio.sleep(backoff)
            else:
                # Clear keypair from memory if we're done with retries
                if 'keypair' in locals():
                    self.wallet_manager.clear_keypair_from_memory(keypair)
        
        # If all retries failed, invoke failed callback
        if not result["success"] and self.on_tx_failed:
            self.on_tx_failed({
                "transfer": transfer.dict(),
                "error": result["error"],
                "timestamp": datetime.now().isoformat()
            })
        
        return result
    
    async def _execute_sol_transfer(
        self, 
        keypair: Keypair, 
        recipient: str, 
        amount: float, 
        blockhash: str
    ) -> Dict[str, Any]:
        """
        Execute a native SOL transfer.
        
        Args:
            keypair: Sender keypair
            recipient: Recipient address
            amount: Amount in SOL
            blockhash: Recent blockhash
            
        Returns:
            Result dictionary
        """
        try:
            # Create transaction
            tx = Transaction()
            tx.recent_blockhash = blockhash
            tx.fee_payer = keypair.pubkey()
            
            # Convert SOL amount to lamports
            lamports = int(amount * 1e9)
            
            # Add transfer instruction
            tx.add(
                transfer(
                    TransferParams(
                        from_pubkey=keypair.pubkey(),
                        to_pubkey=Pubkey.from_string(recipient),
                        lamports=lamports
                    )
                )
            )
            
            # Sign transaction
            tx.sign(keypair)
            
            # Serialize and send transaction
            serialized_tx = tx.serialize()
            tx_bytes = base58.b58encode(serialized_tx).decode('utf-8')
            
            # Send transaction
            resp = await self.async_client.send_raw_transaction(tx_bytes)
            
            if "result" in resp:
                tx_hash = resp["result"]
                
                # Wait for confirmation
                confirmed = await self._wait_for_confirmation(tx_hash)
                
                if confirmed:
                    return {"success": True, "tx_hash": tx_hash, "error": None}
                else:
                    return {"success": False, "tx_hash": tx_hash, "error": "Transaction not confirmed"}
            else:
                error = resp.get("error", {}).get("message", "Unknown error")
                return {"success": False, "tx_hash": None, "error": error}
        
        except Exception as e:
            logger.exception(f"Error executing SOL transfer: {str(e)}")
            return {"success": False, "tx_hash": None, "error": str(e)}
    
    async def _execute_token_transfer(
        self, 
        keypair: Keypair, 
        recipient: str, 
        token_mint: str, 
        amount: float, 
        blockhash: str
    ) -> Dict[str, Any]:
        """
        Execute an SPL token transfer.
        
        Args:
            keypair: Sender keypair
            recipient: Recipient address
            token_mint: Token mint address
            amount: Amount in tokens
            blockhash: Recent blockhash
            
        Returns:
            Result dictionary
        """
        try:
            # Get sender token account
            sender_address = str(keypair.pubkey())
            sender_token_account = self._get_token_account(sender_address, token_mint)
            if not sender_token_account:
                return {
                    "success": False, 
                    "tx_hash": None, 
                    "error": f"No token account found for sender {sender_address} and token {token_mint}"
                }
            
            # Get recipient token account
            recipient_token_account = self._get_token_account(recipient, token_mint)
            if not recipient_token_account:
                # Check if recipient address itself is valid before assuming it's a token account lookup failure
                try:
                    Pubkey.from_string(recipient)
                except ValueError:
                     return {
                        "success": False, 
                        "tx_hash": None, 
                        "error": f"Invalid recipient address format: {recipient}"
                    }

                # If address is valid but account not found, log appropriately (might need account creation)
                logger.warning(f"No token account found for recipient {recipient} and token {token_mint}. Account might need to be created.")
                # Depending on requirements, you might want to return an error or proceed differently here.
                # For now, let's return an error indicating the missing account.
                return {
                    "success": False, 
                    "tx_hash": None, 
                    "error": f"No token account found for recipient {recipient} and token {token_mint}"
                }
            
            # Get token decimals (assuming 9 decimals for now)
            # In a real implementation, we would fetch this from the token mint
            token_decimals = 9
            token_amount = int(amount * (10 ** token_decimals))
            
            # Execute token transfer
            result = await execute_token_transfer(
                async_client=self.async_client,
                sender_keypair=keypair,
                sender_token_account=sender_token_account,
                recipient_token_account=recipient_token_account,
                amount=token_amount,
                recent_blockhash=blockhash
            )
            
            if result["success"]:
                # Wait for confirmation
                confirmed = await wait_for_token_transfer_confirmation(
                    async_client=self.async_client,
                    tx_hash=result["tx_hash"],
                    timeout_seconds=self.CONFIRMATION_TIMEOUT
                )
                
                if confirmed:
                    return result
                else:
                    return {
                        "success": False, 
                        "tx_hash": result["tx_hash"], 
                        "error": "Transaction not confirmed"
                    }
            
            return result
        
        except Exception as e:
            logger.exception(f"Error executing token transfer: {str(e)}")
            return {"success": False, "tx_hash": None, "error": str(e)}
    
    def _get_token_account(self, wallet_address: str, token_mint: str) -> Optional[str]:
        """
        Get token account for a wallet and token mint, with caching.
        
        Args:
            wallet_address: Wallet address
            token_mint: Token mint address
            
        Returns:
            Token account address or None if not found
        """
        cache_key = f"{wallet_address}:{token_mint}"
        
        # Check cache first
        if cache_key in self._token_account_cache:
            return self._token_account_cache[cache_key]
        
        # Look up token account
        token_account = get_token_account(self.client, wallet_address, token_mint)
        
        # Cache the result
        if token_account:
            self._token_account_cache[cache_key] = token_account
        
        return token_account
    
    async def _wait_for_confirmation(self, tx_hash: str) -> bool:
        """
        Waits for transaction confirmation.
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            True if confirmed, False otherwise
        """
        start_time = time.time()
        
        while time.time() - start_time < self.CONFIRMATION_TIMEOUT:
            try:
                resp = await self.async_client.get_signature_statuses([tx_hash])
                
                if "result" in resp and resp["result"]["value"][0]:
                    status = resp["result"]["value"][0]
                    
                    if status.get("confirmations") is None and status.get("confirmationStatus") == "finalized":
                        return True
                    
                    if status.get("err"):
                        logger.error(f"Transaction error: {status.get('err')}")
                        return False
                
                # Wait before checking again
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error checking transaction status: {str(e)}")
                await asyncio.sleep(2)
        
        logger.warning(f"Transaction confirmation timeout for {tx_hash}")
        return False
    
    async def retry_with_increased_fee(self, transfer: TransferOp, sender_secret: str, retry_count: int) -> Dict[str, Any]:
        """
        Retries a failed transfer with increased fee.
        
        Args:
            transfer: Transfer operation to retry
            sender_secret: Encrypted sender secret key
            retry_count: Current retry count
            
        Returns:
            Result dictionary with success status and transaction hash
        """
        logger.info(
            f"Retrying transfer with increased fee (attempt {retry_count})",
            extra={"transfer_id": id(transfer), "retry_count": retry_count}
        )
        
        # Get a new fee estimate
        fee_estimate = self.fee_oracle.get_current_fee_estimate()
        
        # Increase fee by 20% per retry attempt
        fee_multiplier = 1.0 + (0.2 * retry_count)
        increased_fee = int(fee_estimate.lamports * fee_multiplier)
        
        logger.info(
            f"Using increased fee: {increased_fee} lamports (base: {fee_estimate.lamports})",
            extra={"base_fee": fee_estimate.lamports, "increased_fee": increased_fee}
        )
        
        # Update transfer with new fee
        transfer.fee_lamports = increased_fee
        
        # Execute with increased fee
        return await self.execute_transfer(transfer, sender_secret) 