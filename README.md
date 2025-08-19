# NinjaBot - Solana Volume Trading Telegram Bot

A sophisticated Telegram bot for automated Solana volume trading, token creation, and wallet management with advanced PumpFun integration.

## 🚀 Features

### **Core Trading Operations**
- **Volume Generation**: Automated volume trading with customizable strategies
- **Token Creation**: Create new tokens on Solana with PumpFun integration
- **SPL Token Trading**: Buy/sell operations with multiple execution modes
- **Wallet Bundling**: Advanced bundling operations for coordinated trading

### **Wallet Management**
- **Multi-Wallet Support**: Manage mother wallets and child wallets
- **Automated Funding**: Intelligent wallet funding with verification
- **Return Funds**: Secure fund consolidation with balance verification
- **Balance Monitoring**: Real-time balance tracking and alerts

### **Advanced Features**
- **Transaction Verification**: Robust verification system for all operations
- **Rate Limiting**: Smart rate limiting to avoid API throttling
- **Session Management**: Persistent session handling with automatic refresh
- **Error Recovery**: Comprehensive error handling and retry mechanisms
- **Structured Logging**: Detailed logging with JSON formatting for observability

## 🏗️ Architecture

```
ninjabot/
├── bot/
│   ├── api/                 # API clients and integrations
│   │   ├── api_client.py    # Core API client
│   │   └── pumpfun_client.py # PumpFun specific client
│   ├── config/              # Configuration management
│   ├── handlers/            # Telegram bot handlers
│   │   ├── start_handler.py         # Main bot interactions
│   │   ├── wallet_handler.py        # Wallet operations
│   │   ├── token_trading_handler.py # Trading operations
│   │   ├── token_creation_handler.py # Token creation
│   │   └── bundling_handler.py      # Bundling operations
│   ├── utils/               # Utility modules
│   │   ├── api_verification_utils.py # Transaction verification
│   │   ├── wallet_storage.py        # Wallet persistence
│   │   ├── message_utils.py         # Message formatting
│   │   └── validation_utils.py      # Input validation
│   ├── events/              # Event system
│   └── state/               # State management
├── data/                    # Data storage
├── logs/                    # Application logs
└── temp/                    # Temporary files
```

## 📋 Prerequisites

- Python 3.8+
- Solana CLI tools (optional, for advanced operations)
- Telegram Bot Token
- API access credentials

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd ninjabot
```

### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
Create a `.env` file in the root directory:
```env
# Required
BOT_TOKEN=your_telegram_bot_token_here
API_BASE_URL=https://solanaapivolume.onrender.com

# Optional
LOG_LEVEL=INFO
BALANCE_POLL_INTERVAL=3
CONVERSATION_TIMEOUT=300
```

### 5. Initialize Data Directories
```bash
mkdir -p data/mother_wallets data/children_wallets data/bundled_wallets
mkdir -p logs temp
```

## 🚀 Usage

### Starting the Bot
```bash
python run_bot.py
```

### Basic Commands
- `/start` - Initialize the bot and access main menu
- Use inline keyboards to navigate through different operations

### Main Operations

#### **Volume Generation**
1. Select "Volume Generation" from main menu
2. Choose wallet (create new or use existing)
3. Configure child wallets and volume parameters
4. Preview and confirm execution
5. Monitor progress through real-time updates

#### **Token Creation**
1. Select "Bundling" → "Token Creation"
2. Configure token parameters (name, symbol, description)
3. Upload token image via Telegram
4. Set buy amounts for bundled wallets
5. Execute token creation with automated bundling

#### **Wallet Management**
1. Access "Bundler Management" from main menu
2. View wallet balances and token holdings
3. Execute sell operations with percentage-based controls
4. Fund or return funds from wallets

## ⚙️ Configuration

### **Trading Parameters**
- **Min Child Wallets**: 10
- **Max Child Wallets**: 100
- **Min Volume**: 0.01 SOL
- **Service Fee**: 0.1%

### **Verification Settings**
- **Funding Timeout**: 7 minutes base + 2 minutes extension
- **Balance Threshold**: 0.02 SOL for verification
- **Max Verification Time**: 10 minutes hard cap

### **Polling Configuration**
- **Balance Poll Interval**: 3 seconds
- **Conversation Timeout**: 5 minutes
- **Gas Spike Threshold**: 1.5x average

## 🔒 Security Features

- **Private Key Protection**: Secure storage and handling
- **Session Management**: Automatic token refresh and validation
- **Transaction Verification**: Multi-layer verification system
- **Error Recovery**: Graceful handling of network issues

## 📊 Monitoring & Logging

### **Log Files**
- Logs are stored in `logs/` directory
- JSON-formatted structured logging
- 14-day retention with daily rotation
- Real-time console output

### **Monitoring Features**
- Real-time balance tracking
- Transaction status monitoring
- Performance metrics logging
- Error tracking and alerting

## 🧪 Testing

The project includes comprehensive tests:

```bash
# Run specific tests
python test_balance_thresholds.py
python test_return_funds.py
python test_volume_generation_fix.py

# Run with pytest (if available)
pytest tests/
```

## 🛠️ Development

### **Code Structure**
- **Handlers**: Telegram bot interaction logic
- **API Clients**: External service integrations
- **Utils**: Shared utility functions
- **Config**: Configuration management
- **Events**: Event-driven architecture components

### **Key Design Patterns**
- **Conversation State Management**: Robust state tracking
- **Event-Driven Architecture**: Decoupled component communication
- **Verification Patterns**: Consistent transaction verification
- **Error Recovery**: Comprehensive error handling strategies

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Implement changes with tests
4. Follow existing code style and patterns
5. Submit a pull request

### **Code Style**
- Follow PEP 8 conventions
- Use type hints where applicable
- Include comprehensive docstrings
- Maintain test coverage

## 📝 License

[Specify your license here]

## 🆘 Support

For issues and questions:
1. Check the logs in `logs/` directory
2. Review configuration in `.env` file
3. Ensure all dependencies are installed
4. Verify API credentials and connectivity

## 🔄 Recent Updates

- Enhanced transaction verification system
- Improved wallet address derivation
- Advanced session management
- Robust error recovery mechanisms
- Post-transaction verification for all operations

---

**⚠️ Disclaimer**: This bot involves financial transactions on the Solana blockchain. Use at your own risk and ensure you understand the implications of automated trading operations.
