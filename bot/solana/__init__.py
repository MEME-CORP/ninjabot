"""
Solana integration for the Volume Bot.

This package contains modules for interacting with the Solana blockchain,
including wallet management, transaction execution, fee estimation, and scheduling.

Note: We start on devnet for extensive testing before moving to mainnet.
Mainnet has more congestion than devnet, so transaction logic includes
retry mechanisms and fee spike detection.
"""

from bot.solana.models import WalletInfo, TransferOp, Schedule, FeeEstimate
from bot.solana.wallet_manager import WalletManager
from bot.solana.fee_oracle import FeeOracle
from bot.solana.scheduler import Scheduler
from bot.solana.fee_collector import FeeCollector
from bot.solana.tx_executor import TxExecutor
from bot.solana.token_program import (
    get_token_account,
    create_token_account_instruction,
    create_token_transfer_instruction,
    execute_token_transfer,
    wait_for_token_transfer_confirmation
)
from bot.solana.integration import SolanaVolumeOrchestrator 