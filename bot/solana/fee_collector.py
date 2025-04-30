"""
Service fee collection for Solana transfers.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger

from bot.config import SERVICE_FEE_RATE
from bot.solana.models import TransferOp, Schedule

class FeeCollector:
    """
    Calculates and collects service fees for Solana transfers.
    """
    
    def __init__(self, service_wallet: str):
        """
        Initialize the fee collector.
        
        Args:
            service_wallet: Address to receive service fees
        """
        self.service_wallet = service_wallet
        logger.info(f"FeeCollector initialized with service wallet: {service_wallet}")
    
    def calculate_fee(self, amount: float, token_decimals: int = 9) -> float:
        """
        Calculates service fee for a given transfer amount.
        
        Args:
            amount: Transfer amount
            token_decimals: Number of decimals in token
            
        Returns:
            Fee amount
        """
        fee = amount * SERVICE_FEE_RATE
        
        # Round to token precision
        scale = 10 ** -token_decimals
        fee = round(fee / scale) * scale
        
        logger.debug(
            f"Calculated fee: {fee} for amount: {amount}",
            extra={"amount": amount, "fee": fee, "rate": SERVICE_FEE_RATE}
        )
        
        return fee
    
    def adjust_schedule(self, schedule: Schedule, total_funded: float) -> Schedule:
        """
        Adjusts schedule to include fees while respecting total funded amount.
        
        Args:
            schedule: Original schedule
            total_funded: Total funded amount
            
        Returns:
            Adjusted schedule
        """
        # Calculate total service fee
        service_fee_total = total_funded * SERVICE_FEE_RATE
        remaining_volume = total_funded - service_fee_total
        
        # Scale down transfers to account for fees
        scaling_factor = remaining_volume / schedule.total_volume
        
        for transfer in schedule.transfers:
            # Only scale non-fee transfers (those not going to service wallet)
            if transfer.to_address != self.service_wallet:
                transfer.amount *= scaling_factor
        
        # Update schedule with new totals
        schedule.total_volume = total_funded
        schedule.service_fee_total = service_fee_total
        
        # Add fee transfers
        self._add_fee_transfers(schedule, service_fee_total)
        
        logger.info(
            f"Adjusted schedule for {total_funded} total with {service_fee_total} fee",
            extra={
                "total_funded": total_funded,
                "service_fee": service_fee_total,
                "scale_factor": scaling_factor
            }
        )
        
        return schedule
    
    def _add_fee_transfers(self, schedule: Schedule, total_fee: float):
        """
        Adds fee transfers to a schedule.
        
        Args:
            schedule: Schedule to modify
            total_fee: Total fee amount
        """
        # Calculate number of fee transfers
        n_fee_transfers = min(5, len(schedule.child_wallets))
        fee_per_transfer = total_fee / n_fee_transfers
        
        # Get latest timestamp from regular transfers
        if schedule.transfers:
            latest_timestamp = max(t.estimated_time for t in schedule.transfers)
            start_time = latest_timestamp + timedelta(seconds=30)
        else:
            start_time = datetime.now() + timedelta(minutes=5)
        
        # Create fee transfers
        fee_transfers = []
        for i in range(n_fee_transfers):
            sender = schedule.child_wallets[i % len(schedule.child_wallets)]
            timestamp = start_time + timedelta(seconds=i * 30)
            
            transfer = TransferOp(
                from_address=sender,
                to_address=self.service_wallet,
                amount=fee_per_transfer,
                token_mint=schedule.token_mint,
                estimated_time=timestamp
            )
            
            fee_transfers.append(transfer)
        
        # Add fee transfers to schedule
        schedule.transfers.extend(fee_transfers)
        
        logger.info(
            f"Added {n_fee_transfers} service fee transfers to schedule",
            extra={"fee_transfers": n_fee_transfers, "fee_per_transfer": fee_per_transfer}
        )
    
    def generate_fee_transfer(self, main_transfer: TransferOp) -> TransferOp:
        """
        Creates a fee transfer operation to follow the main transfer.
        
        Args:
            main_transfer: The main transfer
            
        Returns:
            Fee transfer operation
        """
        fee_amount = self.calculate_fee(main_transfer.amount)
        
        fee_transfer = TransferOp(
            from_address=main_transfer.from_address,
            to_address=self.service_wallet,
            amount=fee_amount,
            token_mint=main_transfer.token_mint,
            estimated_time=main_transfer.estimated_time + timedelta(seconds=10)
        )
        
        logger.debug(
            f"Generated fee transfer for {fee_amount} tokens",
            extra={"main_amount": main_transfer.amount, "fee_amount": fee_amount}
        )
        
        return fee_transfer 