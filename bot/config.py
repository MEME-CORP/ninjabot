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