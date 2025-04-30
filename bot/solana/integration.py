"""
Integration module that combines the Solana components.

This module demonstrates how to instantiate and use the various Solana
components together to create a complete workflow.
"""

import asyncio
import uuid
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from loguru import logger
from collections import defaultdict

from bot.solana.models import WalletInfo, TransferOp, Schedule
from bot.solana.wallet_manager import WalletManager
from bot.solana.fee_oracle import FeeOracle
from bot.solana.scheduler import Scheduler
from bot.solana.fee_collector import FeeCollector
from bot.solana.tx_executor import TxExecutor

class SolanaVolumeOrchestrator:
    """
    Orchestrates the complete Solana volume generation workflow.
    
    This class combines all the individual Solana components into a single
    workflow for generating volume on the Solana blockchain.
    """
    
    def __init__(self,
                 network: str = "devnet",
                 service_wallet: Optional[str] = None,
                 wallet_manager: Optional[WalletManager] = None,
                 fee_oracle: Optional[FeeOracle] = None,
                 scheduler: Optional[Scheduler] = None,
                 fee_collector: Optional[FeeCollector] = None,
                 tx_executor: Optional[TxExecutor] = None):
        """
        Initialize the orchestrator.
        
        Args:
            network: Solana network to use (devnet or mainnet)
            service_wallet: Service fee wallet address (optional)
            wallet_manager: Optional WalletManager instance. If None, creates a new one.
            fee_oracle: Optional FeeOracle instance. If None, creates a new one.
            scheduler: Optional Scheduler instance. If None, creates a new one.
            fee_collector: Optional FeeCollector instance. If None, creates a new one.
            tx_executor: Optional TxExecutor instance. If None, creates a new one.
        """
        self.network = network
        self.event_callbacks = defaultdict(list)
        
        # Store the service wallet address
        self.service_wallet = service_wallet

        # Initialize components
        self.wallet_manager = wallet_manager if wallet_manager else WalletManager(network=network)
        self.fee_oracle = fee_oracle if fee_oracle else FeeOracle(network=network)
        self.scheduler = scheduler if scheduler else Scheduler()
        
        if service_wallet:
            self.fee_collector = fee_collector if fee_collector else FeeCollector(service_wallet=service_wallet)
        else:
            self.fee_collector = None
        
        # Initialize transaction executor
        self.tx_executor = tx_executor if tx_executor else TxExecutor(
            wallet_manager=self.wallet_manager,
            fee_oracle=self.fee_oracle,
            network=network,
            on_tx_sent=self._on_tx_sent,
            on_tx_confirmed=self._on_tx_confirmed,
            on_tx_failed=self._on_tx_failed,
            on_tx_retry=self._on_tx_retry
        )
        
        logger.info(f"SolanaVolumeOrchestrator initialized on {network}")
    
    def create_mother_wallet(self) -> WalletInfo:
        """
        Creates a new mother wallet.
        
        Returns:
            WalletInfo object for mother wallet
        """
        return self.wallet_manager.create_mother()
    
    def import_mother_wallet(self, private_key: str) -> WalletInfo:
        """
        Imports an existing mother wallet.
        
        Args:
            private_key: The private key to import
            
        Returns:
            WalletInfo object for mother wallet
        """
        return self.wallet_manager.import_mother(private_key)
    
    def derive_child_wallets(self, n: int, mother_secret: str) -> List[WalletInfo]:
        """
        Derives child wallets from mother wallet.
        
        Args:
            n: Number of child wallets to derive
            mother_secret: Mother wallet encrypted secret key
            
        Returns:
            List of WalletInfo objects for child wallets
        """
        return self.wallet_manager.derive_children(n, mother_secret)
    
    def generate_schedule(
        self, 
        mother_wallet: str, 
        child_wallets: List[str], 
        token_mint: str, 
        total_volume: float
    ) -> Schedule:
        """
        Generates a transfer schedule.
        
        Args:
            mother_wallet: Mother wallet address
            child_wallets: List of child wallet addresses
            token_mint: Token contract address
            total_volume: Total volume to transfer
            
        Returns:
            Schedule object with transfers
        """
        return self.scheduler.generate_schedule(
            mother_wallet=mother_wallet,
            child_wallets=child_wallets,
            token_mint=token_mint,
            total_volume=total_volume,
            service_wallet=self.service_wallet
        )
    
    def adjust_schedule_for_funding(self, schedule: Schedule, funded_amount: float) -> Schedule:
        """
        Adjusts a schedule based on the actual funded amount.
        
        Args:
            schedule: Original schedule
            funded_amount: Actual funded amount
            
        Returns:
            Adjusted schedule
        """
        if self.fee_collector:
            return self.fee_collector.adjust_schedule(schedule, funded_amount)
        
        # If no fee collector, just scale the transfers
        scaling_factor = funded_amount / schedule.total_volume
        
        for transfer in schedule.transfers:
            transfer.amount *= scaling_factor
        
        schedule.total_volume = funded_amount
        
        return schedule
    
    async def execute_schedule(self, schedule: Schedule, wallet_secrets: Dict[str, str]) -> Schedule:
        """
        Executes a transfer schedule.
        
        Args:
            schedule: Schedule to execute
            wallet_secrets: Dictionary mapping wallet addresses to encrypted secret keys
            
        Returns:
            Updated schedule with execution results
        """
        # Notify schedule started
        if self.event_callbacks["on_schedule_started"]:
            self.event_callbacks["on_schedule_started"]({
                "schedule_id": schedule.id,
                "timestamp": datetime.now().isoformat()
            })
        
        # Execute schedule
        updated_schedule = await self.tx_executor.run(schedule, wallet_secrets)
        
        # Notify schedule completed
        if self.event_callbacks["on_schedule_completed"]:
            self.event_callbacks["on_schedule_completed"]({
                "schedule_id": updated_schedule.id,
                "status": updated_schedule.status,
                "timestamp": datetime.now().isoformat()
            })
        
        return updated_schedule
    
    def register_event_callback(self, event_type: str, callback: Callable[[Dict[str, Any]], None]):
        """
        Registers a callback for an event type.
        
        Args:
            event_type: Event type (on_tx_sent, on_tx_confirmed, etc.)
            callback: Callback function that takes event data dict
        """
        if event_type in self.event_callbacks:
            self.event_callbacks[event_type] = callback
            logger.debug(f"Registered callback for event type: {event_type}")
        else:
            logger.warning(f"Unknown event type: {event_type}")
    
    def _on_tx_sent(self, data: Dict[str, Any]):
        """
        Internal handler for transaction sent events.
        
        Args:
            data: Event data
        """
        if self.event_callbacks["on_tx_sent"]:
            self.event_callbacks["on_tx_sent"](data)
    
    def _on_tx_confirmed(self, data: Dict[str, Any]):
        """
        Internal handler for transaction confirmed events.
        
        Args:
            data: Event data
        """
        if self.event_callbacks["on_tx_confirmed"]:
            self.event_callbacks["on_tx_confirmed"](data)
    
    def _on_tx_failed(self, data: Dict[str, Any]):
        """
        Internal handler for transaction failed events.
        
        Args:
            data: Event data
        """
        if self.event_callbacks["on_tx_failed"]:
            self.event_callbacks["on_tx_failed"](data)
    
    def _on_tx_retry(self, data: Dict[str, Any]):
        """
        Internal handler for transaction retry events.
        
        Args:
            data: Event data
        """
        if self.event_callbacks["on_tx_retry"]:
            self.event_callbacks["on_tx_retry"](data)


# Example usage:
async def example_workflow():
    """
    Example of a complete workflow using the SolanaVolumeOrchestrator.
    """
    # Initialize orchestrator
    orchestrator = SolanaVolumeOrchestrator(
        network="devnet",
        service_wallet="ServiceWalletAddressHere123456789"
    )
    
    # Create a mother wallet
    mother_wallet = orchestrator.create_mother_wallet()
    
    # Derive child wallets
    child_wallets = orchestrator.derive_child_wallets(
        n=10,
        mother_secret=mother_wallet.secret_key
    )
    
    # Extract child addresses
    child_addresses = [w.address for w in child_wallets]
    
    # Generate schedule
    schedule = orchestrator.generate_schedule(
        mother_wallet=mother_wallet.address,
        child_wallets=child_addresses,
        token_mint="TokenMintAddressHere123456789",
        total_volume=1000.0
    )
    
    # Prepare wallet secrets for transaction execution
    wallet_secrets = {
        mother_wallet.address: mother_wallet.secret_key
    }
    
    for wallet in child_wallets:
        wallet_secrets[wallet.address] = wallet.secret_key
    
    # Execute schedule
    await orchestrator.execute_schedule(schedule, wallet_secrets)


if __name__ == "__main__":
    # This would be used for standalone testing
    asyncio.run(example_workflow()) 