# Solana Volume Telegram Bot (NinjaBot)

A sophisticated Telegram bot designed to generate legitimate-looking trading volume for SPL tokens on the Solana blockchain. The bot enables users to simulate trading activity by orchestrating random-sized transfers from multiple child wallets at non-overlapping intervals.

## 🚀 Features

### Core Functionality
- **Volume Generation**: Create realistic trading volume patterns for any SPL token
- **Multi-Wallet Management**: Generate and manage multiple child wallets (10-100) from a mother wallet
- **Intelligent Scheduling**: Random transfer amounts and intervals (1-100 seconds) to simulate organic trading
- **Real-time Monitoring**: Live status updates and alerts during execution
- **Gas Spike Protection**: Automatic fee monitoring with configurable thresholds
- **Comprehensive Reporting**: Detailed CSV reports with transaction history

### Advanced Features
- **SPL Token Trading**: Buy/sell operations with configurable strategies
- **Bundle Operations**: Create and manage bundled wallet operations
- **PumpFun Integration**: Support for PumpFun token operations
- **Profit Strategies**: Automated profit-taking mechanisms
- **Balance Monitoring**: Real-time wallet balance tracking
- **Error Recovery**: Automatic retry logic with exponential backoff

## 📋 Requirements

### System Requirements
- Python 3.8+
- Telegram Bot Token
- Solana RPC endpoint access
- Supabase database (for persistence)

### Dependencies
```
python-telegram-bot==20.4
pydantic==1.10.8
requests==2.31.0
python-dotenv==1.0.0
loguru==0.7.0
```

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd ninjabot
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   Create a `.env` file in the root directory:
   ```env
   BOT_TOKEN=your_telegram_bot_token_here
   API_BASE_URL=https://solanaapivolume.onrender.com
   LOG_LEVEL=INFO
   BALANCE_POLL_INTERVAL=3
   CONVERSATION_TIMEOUT=300
   ```

## 🚀 Usage

### Starting the Bot
```bash
python run_bot.py
```

### Basic Workflow
1. **Start**: Send `/start` to the bot
2. **Wallet Setup**: Choose to create new or import existing mother wallet
3. **Configuration**: Set number of child wallets (10-100)
4. **Volume Setup**: Define target volume and token address
5. **Preview**: Review generated schedule and fee estimates
6. **Funding**: Fund the mother wallet with required SOL
7. **Execution**: Monitor real-time progress and alerts
8. **Completion**: Receive summary report and CSV download

### Advanced Operations

#### SPL Token Trading
- Configure buy/sell strategies
- Set profit thresholds
- Automated execution modes
- Real-time P&L tracking

#### Bundle Operations
- Create token bundles
- Manage airdrop wallets
- Batch operations
- Coordinated trading strategies

## 📁 Project Structure

```
ninjabot/
├── bot/                          # Main bot package
│   ├── api/                      # External API clients
│   │   ├── api_client.py         # Generic API client
│   │   └── pumpfun_client.py     # PumpFun specific client
│   ├── config/                   # Configuration management
│   │   ├── __init__.py           # Core configuration
│   │   └── spl_config.py         # SPL token configurations
│   ├── events/                   # Event system
│   │   └── event_system.py       # Event handling
│   ├── handlers/                 # Telegram command handlers
│   │   ├── start_handler.py      # Start command handler
│   │   └── bundling_handler.py   # Bundle operations handler
│   ├── scripts/                  # Trading and execution scripts
│   │   ├── spl_buy_sell_script.py    # SPL token trading
│   │   ├── swap_executor.py           # Swap execution logic
│   │   ├── wallet_swap_manager.py     # Wallet management
│   │   ├── amount_calculator.py       # Volume calculations
│   │   ├── buy_sell_config.py         # Trading configuration
│   │   └── result_reporter.py         # Results reporting
│   ├── state/                    # State management
│   │   └── session_manager.py    # Session handling
│   ├── utils/                    # Utility functions
│   │   ├── balance_poller.py     # Balance monitoring
│   │   ├── wallet_storage.py     # Wallet persistence
│   │   ├── message_utils.py      # Message formatting
│   │   └── validation_utils.py   # Input validation
│   └── main.py                   # Main bot entry point
├── data/                         # Data storage
│   ├── configs/                  # Configuration files
│   ├── wallets/                  # Wallet data
│   ├── spl_configs/              # SPL configurations
│   └── spl_sessions/             # Session data
├── logs/                         # Application logs
├── tests/                        # Test files
├── .env                          # Environment variables
├── requirements.txt              # Python dependencies
└── run_bot.py                   # Main entry point
```

## 🔧 Configuration

### Environment Variables
- `BOT_TOKEN`: Telegram bot token from BotFather
- `API_BASE_URL`: Solana API service endpoint
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `BALANCE_POLL_INTERVAL`: Balance check interval in seconds
- `CONVERSATION_TIMEOUT`: Session timeout in seconds

### Trading Configuration
- `MIN_CHILD_WALLETS`: Minimum child wallets (default: 10)
- `MAX_CHILD_WALLETS`: Maximum child wallets (default: 100)
- `MIN_VOLUME`: Minimum volume in SOL (default: 0.01)
- `SERVICE_FEE_RATE`: Service fee rate (default: 0.1%)
- `DEFAULT_GAS_SPIKE_THRESHOLD`: Gas spike threshold multiplier (default: 1.5x)

## 📊 Monitoring and Logging

### Log Files
- Structured JSON logging with loguru
- Daily log rotation with 14-day retention
- Separate log files for different components
- Real-time console output

### Real-time Alerts
- Transaction status updates
- Balance notifications
- Error alerts
- Gas spike warnings
- Completion summaries

## 🔒 Security Features

### Wallet Security
- Encrypted private key storage
- Memory clearing after operations
- Deterministic child wallet generation
- Secure key export functionality

### Transaction Safety
- Gas spike detection and approval
- Balance validation before operations
- Retry logic with exponential backoff
- Transaction confirmation monitoring

## 📈 Reporting

### Summary Reports
- Total transactions executed
- Success/failure rates
- Fee analysis
- Performance metrics

### CSV Export
Format: `timestamp_utc, child_wallet, amount, tx_signature, lamports_used, status`

### Historical Data
- 90-day data retention
- Queryable transaction history
- Session management
- Audit trail

## 🧪 Testing

The project includes comprehensive test suites:
- Unit tests for core functionality
- Integration tests for API clients
- End-to-end workflow tests
- Performance validation tests

Run tests:
```bash
python -m pytest tests/
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Disclaimer

This bot is designed for legitimate volume generation and testing purposes. Users are responsible for compliance with applicable laws and regulations. The authors are not responsible for any misuse of this software.

## 🔗 Links

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Solana Documentation](https://docs.solana.com/)
- [PumpFun Documentation](https://docs.pumpfun.com/)

## 📞 Support

For support and questions:
- Create an issue in the repository
- Check the logs for error details
- Review the PRD.txt for detailed specifications

---

**Version**: 1.0.0  
**Last Updated**: 2025-01-09
