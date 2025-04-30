"""
Scheduler for Solana transfers.
"""

import random
import uuid
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger

from bot.solana.models import TransferOp, Schedule
from bot.config import SERVICE_FEE_RATE

class Scheduler:
    """
    Generates random transfer schedules for Solana token transfers.
    """
    
    # Maximum time between transfers in seconds
    MAX_INTERVAL = 100
    
    def __init__(self):
        """Initialize the scheduler."""
        logger.info("Scheduler initialized")
    
    def generate_schedule(
        self, 
        mother_wallet: str,
        child_wallets: List[str],
        token_mint: str,
        total_volume: float,
        service_wallet: Optional[str] = None
    ) -> Schedule:
        """
        Generates a random transfer schedule.
        
        Args:
            mother_wallet: Mother wallet address
            child_wallets: List of child wallet addresses
            token_mint: Token contract address
            total_volume: Total volume to transfer
            service_wallet: Service fee wallet address (optional)
            
        Returns:
            Schedule object with transfers
        """
        # Calculate service fee
        service_fee_total = total_volume * SERVICE_FEE_RATE
        remaining_volume = total_volume - service_fee_total
        
        logger.info(
            f"Generating schedule for {total_volume} tokens with {service_fee_total} fee",
            extra={
                "total_volume": total_volume,
                "service_fee": service_fee_total,
                "remaining_volume": remaining_volume
            }
        )
        
        # Create random transfers
        transfers = []
        total_transferred = 0
        
        # Determine number of transfers (2-3 per child wallet)
        n_wallets = len(child_wallets)
        transfers_per_wallet = random.randint(2, 3)
        n_transfers = n_wallets * transfers_per_wallet
        
        # Create non-overlapping timestamps over a period
        now = datetime.now()
        timestamps = []
        
        for i in range(n_transfers):
            # Random offset from current time (up to 24 hours)
            max_seconds = min(24 * 60 * 60, n_transfers * self.MAX_INTERVAL)
            offset = random.randint(0, max_seconds)
            timestamp = now + timedelta(seconds=offset)
            timestamps.append(timestamp)
        
        # Sort timestamps
        timestamps.sort()
        
        # Assign random amounts for each transfer
        for i in range(n_transfers - 1):
            # Select random sender and receiver
            sender_idx = i % len(child_wallets)
            receiver_idx = (sender_idx + random.randint(1, len(child_wallets) - 1)) % len(child_wallets)
            
            sender = child_wallets[sender_idx]
            receiver = child_wallets[receiver_idx]
            
            # Determine a random amount for this transfer
            max_possible = remaining_volume - total_transferred
            if n_transfers - i > 1:
                # Leave some for remaining transfers
                max_amount = max_possible * 0.8
                amount = random.uniform(max_possible * 0.01, max_amount)
            else:
                # Last transfer, use remaining amount
                amount = max_possible
            
            total_transferred += amount
            
            # Create transfer operation
            transfer = TransferOp(
                from_address=sender,
                to_address=receiver,
                amount=amount,
                token_mint=token_mint,
                estimated_time=timestamps[i]
            )
            
            transfers.append(transfer)
        
        # Last transfer - use exact remaining amount to ensure total matches
        remaining_amount = remaining_volume - total_transferred
        if remaining_amount > 0:
            sender_idx = (n_transfers - 1) % len(child_wallets)
            receiver_idx = (sender_idx + random.randint(1, len(child_wallets) - 1)) % len(child_wallets)
            
            sender = child_wallets[sender_idx]
            receiver = child_wallets[receiver_idx]
            
            transfer = TransferOp(
                from_address=sender,
                to_address=receiver,
                amount=remaining_amount,
                token_mint=token_mint,
                estimated_time=timestamps[-1]
            )
            
            transfers.append(transfer)
        
        # If service wallet is provided, add service fee transfers
        if service_wallet and service_fee_total > 0:
            self._add_service_fee_transfers(
                transfers=transfers,
                child_wallets=child_wallets,
                service_wallet=service_wallet,
                token_mint=token_mint,
                service_fee_total=service_fee_total
            )
        
        # Create and return schedule
        schedule_id = str(uuid.uuid4())
        schedule = Schedule(
            id=schedule_id,
            mother_wallet=mother_wallet,
            child_wallets=child_wallets,
            token_mint=token_mint,
            total_volume=total_volume,
            service_fee_total=service_fee_total,
            transfers=transfers
        )
        
        logger.info(
            f"Generated schedule with {len(transfers)} transfers",
            extra={"schedule_id": schedule_id, "transfer_count": len(transfers)}
        )
        
        return schedule
    
    def _add_service_fee_transfers(
        self,
        transfers: List[TransferOp],
        child_wallets: List[str],
        service_wallet: str,
        token_mint: str,
        service_fee_total: float
    ):
        """
        Adds service fee transfers to the schedule.
        
        Args:
            transfers: List of existing transfers
            child_wallets: List of child wallet addresses
            service_wallet: Service fee wallet address
            token_mint: Token contract address
            service_fee_total: Total service fee amount
        """
        # Calculate fee per transfer
        n_fee_transfers = min(5, len(child_wallets))
        fee_per_transfer = service_fee_total / n_fee_transfers
        
        # Get latest timestamp from regular transfers
        if transfers:
            latest_timestamp = max(t.estimated_time for t in transfers)
            start_time = latest_timestamp + timedelta(seconds=30)
        else:
            start_time = datetime.now() + timedelta(minutes=5)
        
        # Add fee transfers after regular transfers
        for i in range(n_fee_transfers):
            sender = random.choice(child_wallets)
            timestamp = start_time + timedelta(seconds=i * 30)
            
            transfer = TransferOp(
                from_address=sender,
                to_address=service_wallet,
                amount=fee_per_transfer,
                token_mint=token_mint,
                estimated_time=timestamp
            )
            
            transfers.append(transfer)
            
        logger.info(
            f"Added {n_fee_transfers} service fee transfers",
            extra={"fee_transfers": n_fee_transfers, "fee_per_transfer": fee_per_transfer}
        ) 