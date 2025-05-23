"""
Volume generation service for the Solana Volume Bot.

This module implements the OrganicScheduleGenerator for generating organic-looking
transfer schedules for Solana SPL tokens.
"""

import random
import time
import math
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal

class TradeInstruction:
    """
    Represents a single trade instruction in a volume generation schedule.
    """
    def __init__(
        self,
        from_wallet_pubkey: str,
        to_wallet_pubkey: str,
        amount: int,
        execute_at_timestamp: float,
        token_mint: str
    ):
        self.from_wallet_pubkey = from_wallet_pubkey
        self.to_wallet_pubkey = to_wallet_pubkey
        self.amount = amount
        self.execute_at_timestamp = execute_at_timestamp
        self.token_mint = token_mint
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the instruction to a dictionary."""
        return {
            "fromWalletPubkey": self.from_wallet_pubkey,
            "toWalletPubkey": self.to_wallet_pubkey,
            "amount": str(self.amount),  # Convert to string to handle large integers
            "executeAtTimestamp": self.execute_at_timestamp,
            "tokenMint": self.token_mint
        }

class OrganicScheduleConfig:
    """
    Configuration for generating an organic schedule.
    """
    def __init__(
        self,
        num_child_wallets: int,
        child_wallet_pubkeys: List[str],
        total_volume: int,
        token_mint: str,
        token_decimals: int,
        min_interval_sec: int,
        max_interval_sec: int,
        execution_start_time: Optional[float] = None
    ):
        self.num_child_wallets = num_child_wallets
        self.child_wallet_pubkeys = child_wallet_pubkeys
        self.total_volume = total_volume
        self.token_mint = token_mint
        self.token_decimals = token_decimals
        self.min_interval_sec = min_interval_sec
        self.max_interval_sec = max_interval_sec
        self.execution_start_time = execution_start_time or time.time()

class OrganicScheduleGenerator:
    """
    Generates schedules for token transfers with randomized amounts,
    timings, and wallet pairings to achieve organicity.
    """
    
    @staticmethod
    def generate(config: OrganicScheduleConfig) -> List[TradeInstruction]:
        """
        Generate an organic schedule of trades based on the provided configuration.
        
        Args:
            config: The configuration for the schedule generation.
            
        Returns:
            A list of TradeInstruction objects representing the schedule.
        """
        # Validate inputs
        if config.num_child_wallets < 2:
            raise ValueError("Need at least 2 child wallets to generate trades")
        
        if len(config.child_wallet_pubkeys) < config.num_child_wallets:
            raise ValueError(f"Not enough wallet addresses provided. Need {config.num_child_wallets}")
        
        if config.total_volume <= 0:
            raise ValueError("Total volume must be greater than 0")
        
        # Determine number of trades (ensure organic distribution)
        # Use a range of n^2 to 2*n^2 trades for n wallets for more organic interactions
        n = config.num_child_wallets
        min_trades = n * 2  # At least 2 trades per wallet
        max_trades = n * n  # Up to n^2 trades for very organic feel
        
        # Generate a somewhat random but still organic trade count
        num_trades = random.randint(min_trades, max(min_trades + 10, min(max_trades, 50)))

        # Generate unique trade amounts that sum to total_volume
        amounts = OrganicScheduleGenerator._generate_organic_amounts(
            num_trades, 
            config.total_volume, 
            config.token_decimals
        )
        
        # Generate timestamps for each trade
        timestamps = OrganicScheduleGenerator._generate_organic_timestamps(
            num_trades,
            config.min_interval_sec,
            config.max_interval_sec,
            config.execution_start_time
        )
        
        # Generate wallet pairings
        wallet_pairs = OrganicScheduleGenerator._generate_wallet_pairs(
            num_trades,
            config.child_wallet_pubkeys
        )
        
        # Combine into trade instructions
        instructions = []
        for i in range(num_trades):
            from_wallet, to_wallet = wallet_pairs[i]
            instruction = TradeInstruction(
                from_wallet_pubkey=from_wallet,
                to_wallet_pubkey=to_wallet,
                amount=amounts[i],
                execute_at_timestamp=timestamps[i],
                token_mint=config.token_mint
            )
            instructions.append(instruction)
        
        return instructions
    
    @staticmethod
    def _generate_organic_amounts(num_trades: int, total_volume: int, token_decimals: int) -> List[int]:
        """
        Generate a list of amounts that sum to the total volume and appear organic.
        
        Uses a combined approach of random partitioning with varying "chunk sizes"
        to create more realistic-looking trades.
        """
        # Create initial partition using multiple strategies for more variety
        if random.random() < 0.3:
            # Log-normal distribution (common in financial markets)
            mu = math.log(total_volume / num_trades)  # Mean of log values
            sigma = 0.7  # Standard deviation of log values (higher = more variety)
            
            raw_amounts = [math.exp(random.normalvariate(mu, sigma)) for _ in range(num_trades)]
            # Scale to match total_volume
            scaling_factor = total_volume / sum(raw_amounts)
            scaled_amounts = [amount * scaling_factor for amount in raw_amounts]
            amounts = [int(amount) for amount in scaled_amounts]
            
        elif random.random() < 0.6:
            # Power-law distribution (Pareto-like: many small, few large trades)
            alpha = 1.5  # Shape parameter (1 < alpha < 2 gives heavy tail)
            
            # Generate raw values from a power law distribution
            raw_amounts = [random.paretovariate(alpha) for _ in range(num_trades)]
            # Scale to match total_volume
            scaling_factor = total_volume / sum(raw_amounts)
            scaled_amounts = [amount * scaling_factor for amount in raw_amounts]
            amounts = [int(amount) for amount in scaled_amounts]
            
        else:
            # Stick-breaking approach (more uniform but still random)
            remaining = total_volume
            amounts = []
            
            for i in range(num_trades - 1):
                # More variance at the beginning, more uniform at the end
                proportion = random.betavariate(1, max(1, (num_trades - i) / 2))
                amount = int(remaining * proportion)
                # Ensure minimum value is 1
                amount = max(1, amount)
                amounts.append(amount)
                remaining -= amount
            
            # Add the remainder to the last trade
            amounts.append(max(1, remaining))

        # Shuffle the amounts to prevent patterns
        random.shuffle(amounts)
        
        # Ensure no duplicate amounts
        while len(set(amounts)) < len(amounts):
            # Find duplicates and adjust them slightly
            seen = set()
            for i, amount in enumerate(amounts):
                if amount in seen:
                    # Adjust by a small random amount, preserve sum
                    adjustment = random.randint(1, max(2, amount // 20))
                    if i > 0:
                        # Take from previous amount if possible
                        if amounts[i - 1] > adjustment:
                            amounts[i - 1] -= adjustment
                            amounts[i] += adjustment
                        else:
                            # Otherwise add a small value
                            amounts[i] += adjustment
                    else:
                        # For first element, adjust with the last one
                        if amounts[-1] > adjustment:
                            amounts[-1] -= adjustment
                            amounts[i] += adjustment
                        else:
                            amounts[i] += adjustment
                seen.add(amount)
        
        # Final check to ensure total matches exactly
        current_sum = sum(amounts)
        if current_sum != total_volume:
            # Adjust the largest amount to make the sum correct
            diff = total_volume - current_sum
            largest_idx = amounts.index(max(amounts))
            amounts[largest_idx] += diff
        
        return amounts
    
    @staticmethod
    def _generate_organic_timestamps(
        num_trades: int, 
        min_interval_sec: int, 
        max_interval_sec: int, 
        start_time: float
    ) -> List[float]:
        """
        Generate timestamps for each trade with organic-looking intervals.
        
        Args:
            num_trades: Number of trades to schedule
            min_interval_sec: Minimum interval between trades in seconds
            max_interval_sec: Maximum interval between trades in seconds
            start_time: Start time for the first trade (Unix timestamp)
            
        Returns:
            List of timestamps for each trade
        """
        timestamps = [start_time]
        current_time = start_time
        
        # Occasionally create clusters of trades for more realistic patterns
        clustering_enabled = random.random() < 0.7  # 70% chance of enabling clustering
        
        for i in range(1, num_trades):
            if clustering_enabled and random.random() < 0.3:  # 30% chance of a cluster
                # Create a cluster with shorter intervals
                interval = random.uniform(min_interval_sec, min_interval_sec * 2)
            else:
                # Normal interval
                interval = random.uniform(min_interval_sec, max_interval_sec)
            
            current_time += interval
            timestamps.append(current_time)
        
        return timestamps
    
    @staticmethod
    def _generate_wallet_pairs(num_trades: int, wallet_pubkeys: List[str]) -> List[Tuple[str, str]]:
        """
        Generate pairs of wallets for transfers that appear organic.
        
        This ensures all wallets participate and avoids simple patterns like loops.
        
        Args:
            num_trades: Number of trades to generate pairs for
            wallet_pubkeys: List of wallet public keys
            
        Returns:
            List of (from_wallet, to_wallet) tuples
        """
        pairs = []
        num_wallets = len(wallet_pubkeys)
        
        # Keep track of wallet usage to ensure balanced participation
        from_count = {wallet: 0 for wallet in wallet_pubkeys}
        to_count = {wallet: 0 for wallet in wallet_pubkeys}
        
        # Track recent usage to avoid repetition
        recent_from = []
        recent_to = []
        
        for _ in range(num_trades):
            # Determine candidates with lowest usage count
            from_candidates = sorted(wallet_pubkeys, key=lambda w: from_count[w])
            to_candidates = sorted(wallet_pubkeys, key=lambda w: to_count[w])
            
            # Try to avoid recent wallets if possible
            preferred_from = [w for w in from_candidates if w not in recent_from[:3]]
            preferred_to = [w for w in to_candidates if w not in recent_to[:3]]
            
            if not preferred_from:
                preferred_from = from_candidates
            
            if not preferred_to:
                preferred_to = to_candidates
            
            # Select from_wallet with preference to less used wallets
            # Higher probability for wallets at the beginning of the sorted list
            from_wallet = random.choices(
                preferred_from,
                weights=[max(1, num_wallets - i) for i in range(len(preferred_from))],
                k=1
            )[0]
            
            # Select to_wallet with similar logic, but must not be the same as from_wallet
            to_candidates = [w for w in preferred_to if w != from_wallet]
            if not to_candidates:
                # If no candidates left, choose any wallet that's not from_wallet
                to_candidates = [w for w in wallet_pubkeys if w != from_wallet]
            
            to_wallet = random.choices(
                to_candidates, 
                weights=[max(1, len(to_candidates) - i) for i in range(len(to_candidates))],
                k=1
            )[0]
            
            # Update usage counts and recent history
            from_count[from_wallet] += 1
            to_count[to_wallet] += 1
            
            recent_from.append(from_wallet)
            if len(recent_from) > 5:
                recent_from.pop(0)
                
            recent_to.append(to_wallet)
            if len(recent_to) > 5:
                recent_to.pop(0)
            
            pairs.append((from_wallet, to_wallet))
        
        return pairs


class VolumeService:
    """Service for handling volume generation operations."""

    @staticmethod
    def generate_max_volume_schedule(config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate a schedule for maximum volume strategy.
        
        Args:
            config: Configuration for the maximum volume strategy
            
        Returns:
            List of trade instructions as dictionaries
        """
        # Extract configuration values
        organic_config = OrganicScheduleConfig(
            num_child_wallets=config.get("numChildWallets", 10),
            child_wallet_pubkeys=config.get("childWalletPubkeys", []),
            total_volume=int(config.get("totalVolume", 0)),
            token_mint=config.get("tokenMint", ""),
            token_decimals=config.get("tokenDecimals", 9),
            min_interval_sec=config.get("minIntervalSec", 1),
            max_interval_sec=config.get("maxIntervalSec", 100),
            execution_start_time=config.get("executionStartTime")
        )
        
        # Generate the schedule
        instructions = OrganicScheduleGenerator.generate(organic_config)
        
        # Convert to dictionary format
        return [instruction.to_dict() for instruction in instructions] 