"""
Gas fee estimation for Solana.
"""

import time
from typing import List, Dict, Any, Optional, Deque, Tuple
from collections import deque
import requests
from loguru import logger
from solana.rpc.api import Client
from solana.rpc.async_api import AsyncClient
from solders.hash import Hash
from solders.rpc.responses import RpcBlockhash
from datetime import datetime, timedelta, timezone
from statistics import median
import asyncio

from bot.solana.models import FeeEstimate

class FeeOracle:
    """
    Estimates gas fees for Solana transactions and detects fee spikes.
    """
    
    # Spike detection threshold (multiplier of average)
    SPIKE_THRESHOLD = 1.5
    # Number of recent fee estimates to keep
    HISTORY_SIZE = 20
    
    def __init__(self, network="devnet", update_interval_seconds=60):
        """
        Initialize the fee oracle.
        
        Args:
            network: Solana network to use (devnet or mainnet)
            update_interval_seconds: Interval between fee updates
        """
        self.network = network
        self.rpc_url = "https://api.devnet.solana.com" if network == "devnet" else "https://api.mainnet-beta.solana.com"
        self.client = Client(self.rpc_url)
        self.async_client = AsyncClient(self.rpc_url)
        
        # Queue to store recent fee estimates
        self.fee_history: Deque[int] = deque(maxlen=self.HISTORY_SIZE)
        # Initialize with default value
        self.fee_history.append(5000)  # 5000 lamports as default
        
        self._latest_blockhash_info = None
        
        logger.info(f"FeeOracle initialized on {network}")
    
    def get_current_fee_estimate(self) -> FeeEstimate:
        """
        Gets the current fee estimate in lamports.
        
        Returns:
            FeeEstimate object with fee in lamports
        """
        if not self.fee_history:
            # Fetch initial fees if none available
            self._update_fees()

        if not self.fee_history:
            logger.warning("No fee data available, returning default estimate.")
            return FeeEstimate(lamports=5000, is_spike=False)

        # Use the most recent blockhash info if available
        if self._latest_blockhash_info:
            current_fee = self._latest_blockhash_info['result']['value']['feeCalculator']['lamportsPerSignature']
        else:
            # Fallback: Try fetching fee directly (less reliable for spikes)
            try:
                # Use the correct method name for the synchronous client
                resp = self.client.get_latest_blockhash()
                current_fee = resp['result']['value']['feeCalculator']['lamportsPerSignature']
                self._latest_blockhash_info = resp # Cache the latest info
            except Exception as e:
                logger.error(f"Error getting fee estimate: {str(e)}")
                # Fallback to average if direct fetch fails
                current_fee = int(sum(self.fee_history) / len(self.fee_history)) if self.fee_history else 5000

        # Calculate average and detect spike
        average_fee = sum(self.fee_history) / len(self.fee_history)
        is_spike = current_fee > (average_fee * self.SPIKE_THRESHOLD)

        if is_spike:
            logger.warning(f"Fee spike detected: Current={current_fee}, Avg={average_fee:.0f}")

        # Add to history
        self.fee_history.append(current_fee)
        
        fee_estimate = FeeEstimate(
            lamports=current_fee,
            is_spike=is_spike
        )
        
        logger.debug(
            f"Current fee estimate: {current_fee} lamports (spike: {is_spike})",
            extra={"fee": current_fee, "is_spike": is_spike}
        )
        
        return fee_estimate
    
    def _update_fees(self):
        """Update the list of recent fees."""
        try:
            # Use the correct method name for the synchronous client
            resp = self.client.get_latest_blockhash()
            fee = resp['result']['value']['feeCalculator']['lamportsPerSignature']
            self._latest_blockhash_info = resp # Cache the latest info

            self.fee_history.append(fee)
            if len(self.fee_history) > self.HISTORY_SIZE:
                self.fee_history.pop(0)

            logger.debug(f"Updated fees. Current fee: {fee}, History size: {len(self.fee_history)}")

        except Exception as e:
            logger.error(f"Error updating fees: {str(e)}")
    
    def get_blockhash(self) -> Optional[str]:
        """
        Gets a recent blockhash for use in transactions.
        
        Returns:
            Recent blockhash or None if request fails
        """
        try:
            # Use cached value first if available and recent
            if self._latest_blockhash_info:
                 # You might want to add a check here to see how old the cached blockhash is
                 # Blockhashes are typically valid for ~1-2 minutes.
                 # For simplicity, we'll use the cached one if it exists.
                 return self._latest_blockhash_info['result']['value']['blockhash']

            # Fetch a new one if not cached or too old
            # Use the correct method name for the synchronous client
            resp = self.client.get_latest_blockhash()
            self._latest_blockhash_info = resp # Cache the latest info
            return resp['result']['value']['blockhash']
        except Exception as e:
            logger.error(f"Error getting recent blockhash: {str(e)}")
            self._latest_blockhash_info = None # Clear cache on error
            return None 