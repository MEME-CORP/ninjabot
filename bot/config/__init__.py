"""
Configuration package for the Telegram bot.
Core configuration classes and constants.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables")

# API configuration
API_BASE_URL = os.getenv("API_BASE_URL", "https://solanaapivolume-render.onrender.com/")

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Polling configuration
BALANCE_POLL_INTERVAL = int(os.getenv("BALANCE_POLL_INTERVAL", "3"))  # seconds

# Timeout configuration
CONVERSATION_TIMEOUT = int(os.getenv("CONVERSATION_TIMEOUT", "300"))  # 5 minutes

# Service fee configuration
SERVICE_FEE_RATE = 0.001  # 0.1%

# Validation constants
MIN_CHILD_WALLETS = 10
MAX_CHILD_WALLETS = 100
MIN_VOLUME = 0.01  # Minimum volume in SOL
SOLANA_ADDRESS_LENGTH = 44  # Base58 encoded Solana addresses are 44 characters

# Strategy configuration
MIN_INTERVAL_SEC = 1
MAX_INTERVAL_SEC = 100

# Gas spike threshold (default is 1.5x average)
DEFAULT_GAS_SPIKE_THRESHOLD = 1.5

# Conversation states enum values
class ConversationState:
    START = 0
    WALLET_CHOICE = 1
    IMPORT_WALLET = 2
    NUM_CHILD_WALLETS = 3
    VOLUME_AMOUNT = 4
    TOKEN_ADDRESS = 5
    PREVIEW_SCHEDULE = 6
    AWAIT_FUNDING = 7
    CHILD_BALANCES_OVERVIEW = 8  # New state for child wallet balances overview
    EXECUTION = 9
    COMPLETION = 10
    SAVED_WALLET_CHOICE = 11
    CHILD_WALLET_CHOICE = 12

    # New states for volume generation strategies
    STRATEGY_CHOICE = 13
    PROFIT_TOKEN_A = 14
    PROFIT_TOKEN_B = 15
    MAX_TRADE_SIZE = 16
    MIN_PROFIT_THRESHOLD = 17
    PREVIEW_PROFIT_STRATEGY = 18

    # SPL Token Trading States
    SPL_OPERATION_CHOICE = 20
    SPL_TOKEN_PAIR = 21
    SPL_AMOUNT_STRATEGY = 22
    SPL_EXECUTION_MODE = 23
    SPL_PREVIEW = 24
    SPL_EXECUTION = 25

    # Activity Selection States (New for PumpFun Integration)
    ACTIVITY_SELECTION = 30
    ACTIVITY_CONFIRMATION = 31

    # Bundling Workflow States
    BUNDLING_WALLET_SETUP = 40
    IMPORT_AIRDROP_WALLET = 41
    SELECT_EXISTING_AIRDROP_WALLET = 42
    BUNDLED_WALLETS_COUNT = 43
    TOKEN_CREATION_START = 44
    TOKEN_PARAMETER_INPUT = 45
    TOKEN_IMAGE_UPLOAD = 46  # New state for Telegram image upload
    TOKEN_CREATION_PREVIEW = 47
    BUY_AMOUNTS_CONFIG = 48
    BUY_AMOUNTS_INPUT = 49
    BUY_AMOUNTS_PREVIEW = 50
    WALLET_BALANCE_CHECK = 51
    WALLET_FUNDING_REQUIRED = 52
    WALLET_FUNDING_PROGRESS = 53
    RETURN_FUNDS_CONFIRMATION = 54
    RETURN_FUNDS_PROGRESS = 55
    RETURN_FUNDS_COMPLETE = 56
    FINAL_TOKEN_CREATION = 57
    BUNDLE_OPERATION_PROGRESS = 58
    BUNDLE_OPERATION_COMPLETE = 59
    BUNDLED_WALLETS_CHOICE = "bundled_wallets_choice"
    
    # Bundler Management States
    BUNDLER_MANAGEMENT = 60
    AIRDROP_WALLET_SELECTION = 61  # New state for selecting airdrop wallet
    WALLET_BALANCE_OVERVIEW = 62   # New state for showing wallet balances
    TOKEN_LIST = 63                # Updated index
    TOKEN_MANAGEMENT_OPTIONS = 64  # Updated index
    TOKEN_TRADING_OPERATION = 65   # Updated index
    SELL_PERCENTAGE_SELECTION = 66 # Updated index
    SELL_CONFIRM_EXECUTE = 67      # Updated index
    
    # NEW WALLET-FIRST SELLING FLOW - NO BALANCE CHECKING
    SELLING_AIRDROP_SELECTION = 68  # Select airdrop wallet for selling
    SELLING_TOKEN_SELECTION = 69    # Select token after loading child wallets

# Volume generation strategies
class VolumeStrategy:
    MAX_VOLUME = "MAX_VOLUME"
    PROFIT = "PROFIT"

# Callback query prefixes for volume strategies
class CallbackPrefix:
    STRATEGY = "strat_"
    MAX_VOLUME = "max_vol"
    PROFIT = "profit"
    APPROVE_SPIKE = "approve_spike_"
    REJECT_SPIKE = "reject_spike_"
    ABORT_RUN = "abort_run_"
    
    # SPL Trading prefixes
    SPL_OPERATION = "spl_op_"
    SPL_TOKEN_PAIR = "spl_pair_"
    SPL_AMOUNT_STRATEGY = "spl_amt_"
    SPL_EXECUTION_MODE = "spl_exec_"
    SPL_CONFIRM = "spl_confirm_"

    # Activity Selection prefixes
    ACTIVITY = "activity_"
    VOLUME_GENERATION = "volume_gen"
    BUNDLING = "bundling"
    BUNDLER_MANAGEMENT = "bundler_mgmt"

    # Bundling Workflow prefixes
    BUNDLING_SETUP = "bundle_setup_"
    TOKEN_PARAM = "token_param_"
    BUY_AMOUNT = "buy_amt_"
    BATCH_OPERATION = "batch_op_"
    
    # Bundler Management prefixes
    AIRDROP_WALLET_SELECT = "airdrop_select_"  # New prefix for airdrop wallet selection
    WALLET_BALANCE_VIEW = "wallet_balance_"    # New prefix for wallet balance actions
    TOKEN_SELECT = "token_select_"
    TOKEN_OPERATION = "token_op_"
    SELL_PERCENTAGE = "sell_pct_"

# Make everything available at package level
__all__ = [
    'ConversationState',
    'CallbackPrefix', 
    'VolumeStrategy',
    'API_BASE_URL',
    'BOT_TOKEN',
    'SERVICE_FEE_RATE',
    'MIN_CHILD_WALLETS',
    'MAX_CHILD_WALLETS',
    'MIN_VOLUME',
    'SOLANA_ADDRESS_LENGTH',
    'MIN_INTERVAL_SEC',
    'MAX_INTERVAL_SEC',
    'DEFAULT_GAS_SPIKE_THRESHOLD',
    'BALANCE_POLL_INTERVAL',
    'CONVERSATION_TIMEOUT',
    'LOG_LEVEL'
]