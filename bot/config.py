import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables")

# API configuration
API_BASE_URL = os.getenv("API_BASE_URL", "https://solanaapivolume.onrender.com")

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
    EXECUTION = 8
    COMPLETION = 9
    SAVED_WALLET_CHOICE = 10
    CHILD_WALLET_CHOICE = 11

    # New states for volume generation strategies
    STRATEGY_CHOICE = 12
    PROFIT_TOKEN_A = 13
    PROFIT_TOKEN_B = 14
    MAX_TRADE_SIZE = 15
    MIN_PROFIT_THRESHOLD = 16
    PREVIEW_PROFIT_STRATEGY = 17

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