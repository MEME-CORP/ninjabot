"""
Fee service for the Solana Volume Bot.

This module implements the FeeOracle for dynamic fee management
and gas spike detection on the Solana blockchain.
"""

import time
import random
import statistics
from typing import Dict, Any, List, Optional, Tuple

# Default gas spike threshold multiplier
DEFAULT_GAS_SPIKE_THRESHOLD = 1.5

class FeeOracle:
    """
    Monitors Solana network fees and provides recommendations
    for transaction fees to optimize cost and confirmation time.
    """
    
    def __init__(self, rpc_url: Optional[str] = None):
        """
        Initialize the fee oracle.
        
        Args:
            rpc_url: Optional Solana RPC URL for direct queries
        """
        self.rpc_url = rpc_url
        self.recent_fees = []  # Store recent fee observations
        self.last_update = 0  # Last time the fees were updated
        self.update_interval = 60  # Update fees every 60 seconds
        self.gas_spike_threshold = DEFAULT_GAS_SPIKE_THRESHOLD
    
    def fetch_recent_fees(self) -> List[int]:
        """
        Fetch recent transaction fees from the Solana blockchain.
        
        Returns:
            List of recent transaction fees in lamports
        """
        # In a real implementation, this would query the Solana RPC API
        # for recent block data and extract the avg. fee per signature
        
        # This is a placeholder implementation
        # In production, replace with actual RPC call to fetch recent fees
        # Example: Use web3.js getRecentBlockhash() or similar
        
        # Simulated fee range (in lamports) - typical Solana fees
        # would be obtained from the RPC node
        base_fee = 5000  # 0.000005 SOL (5000 lamports)
        
        # Simulate some variance in network conditions
        current_time = time.time()
        time_factor = (current_time % 3600) / 3600  # 0-1 based on position in hour
        
        # Occasionally simulate fee spikes
        if random.random() < 0.05:  # 5% chance of spike
            variance = random.uniform(1.5, 3.0)  # 1.5x to 3x spike
        else:
            # Normal variance
            variance = random.uniform(0.8, 1.2)
            
        # Apply time-based pattern (network tends to be busier at certain times)
        if time_factor > 0.7:  # Busier period
            variance *= 1.2
            
        # Generate 20 recent fees with some random variation
        fees = [
            int(base_fee * variance * random.uniform(0.9, 1.1))
            for _ in range(20)
        ]
        
        return fees
    
    def update_fees(self, force: bool = False) -> None:
        """
        Update the recent fees cache if needed.
        
        Args:
            force: Force an update regardless of the last update time
        """
        current_time = time.time()
        
        # Update if it's been more than update_interval or force update
        if force or (current_time - self.last_update > self.update_interval):
            self.recent_fees = self.fetch_recent_fees()
            self.last_update = current_time
    
    def get_recommended_fee(self) -> int:
        """
        Get the recommended transaction fee.
        
        Returns:
            Recommended fee in lamports
        """
        self.update_fees()
        
        if not self.recent_fees:
            # If no fee data, return a reasonable default (5000 lamports = 0.000005 SOL)
            return 5000
            
        # Calculate average of recent fees
        avg_fee = int(statistics.mean(self.recent_fees))
        
        # Return a slightly higher value than average for better chances of inclusion
        return int(avg_fee * 1.1)
    
    def is_gas_spike(self, current_fee: int) -> bool:
        """
        Determine if the current fee represents a gas spike.
        
        Args:
            current_fee: The current fee in lamports
            
        Returns:
            True if the fee exceeds the gas spike threshold, False otherwise
        """
        self.update_fees()
        
        if not self.recent_fees:
            return False
            
        avg_fee = statistics.mean(self.recent_fees)
        threshold = avg_fee * self.gas_spike_threshold
        
        return current_fee > threshold
    
    def adjust_fee_for_retry(self, previous_fee: int, retry_count: int) -> int:
        """
        Adjust the fee for a retry attempt using binary backoff.
        
        Args:
            previous_fee: The fee used in the previous attempt
            retry_count: The current retry count (1-indexed)
            
        Returns:
            Adjusted fee for the retry
        """
        # Binary backoff - increase by 25%, 50%, 100% for retries 1, 2, 3
        multiplier = 1.0 + (0.25 * (2 ** (min(retry_count, 3) - 1)))
        return int(previous_fee * multiplier)
    
    def set_gas_spike_threshold(self, multiplier: float) -> None:
        """
        Set the gas spike threshold multiplier.
        
        Args:
            multiplier: Multiplier for the gas spike threshold (e.g., 1.5 = 150% of average)
        """
        # Validate input
        if multiplier < 1.0:
            raise ValueError("Gas spike threshold multiplier must be at least 1.0")
            
        self.gas_spike_threshold = multiplier

class FeeManager:
    """
    Manages fees for the volume generation service, including 
    service fees for revenue generation and Solana transaction fees.
    """
    
    def __init__(self, service_fee_rate: float = 0.001, fee_oracle: Optional[FeeOracle] = None):
        """
        Initialize the fee manager.
        
        Args:
            service_fee_rate: Service fee rate as a decimal (default: 0.001 = 0.1%)
            fee_oracle: Optional FeeOracle instance
        """
        self.service_fee_rate = service_fee_rate
        self.fee_oracle = fee_oracle or FeeOracle()
    
    def calculate_service_fee(self, amount: int) -> int:
        """
        Calculate the service fee for a given amount.
        
        Args:
            amount: The transaction amount
            
        Returns:
            Service fee amount
        """
        return int(amount * self.service_fee_rate)
    
    def estimate_solana_fee(self, is_spl_transfer: bool = True) -> int:
        """
        Estimate the Solana transaction fee for a specific transaction type.
        
        Args:
            is_spl_transfer: Whether the transaction is an SPL token transfer (vs. a swap)
            
        Returns:
            Estimated Solana fee in lamports
        """
        base_fee = self.fee_oracle.get_recommended_fee()
        
        # SPL transfers are simpler than swaps
        if is_spl_transfer:
            return base_fee
        else:
            # Swaps are more complex and typically cost more
            # This is a simplified model - actual cost would depend on the specific swap
            return base_fee * 2
    
    def get_total_fees_estimate(self, total_volume: int, num_transfers: int) -> Dict[str, Any]:
        """
        Calculate a comprehensive fee estimate for a volume generation run.
        
        Args:
            total_volume: The total volume to be transferred
            num_transfers: The number of transfers in the schedule
            
        Returns:
            Dictionary with fee estimates:
                - serviceFee: The total service fee
                - estimatedSolanaFees: The estimated Solana blockchain fees
                - totalFees: The total of all fees
        """
        # Calculate service fee
        service_fee = self.calculate_service_fee(total_volume)
        
        # Estimate Solana fees
        solana_fee_per_tx = self.estimate_solana_fee()
        estimated_solana_fees = solana_fee_per_tx * num_transfers
        
        # Convert to SOL (for display purposes)
        solana_fees_sol = estimated_solana_fees / 1_000_000_000  # 1 SOL = 10^9 lamports
        
        return {
            "serviceFee": service_fee,
            "serviceFeePercent": f"{self.service_fee_rate * 100:.2f}%",
            "estimatedSolanaFees": estimated_solana_fees,
            "estimatedSolanaFeesSol": solana_fees_sol,
            "solanaFeePerTx": solana_fee_per_tx,
            "totalFees": service_fee + estimated_solana_fees,
            "numTransfers": num_transfers
        } 