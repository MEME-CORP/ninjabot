# Solana Volume Bot

A Telegram bot that orchestrates randomized SPL-token transfers on Solana to create legitimate-looking trading volume.

## Features

- Create or import a mother wallet
- Automatically generate multiple child wallets
- Create random transfer schedules between wallets
- Show a preview of the transfer schedule
- Real-time balance checking
- Transaction status updates
- 0.1% service fee on all transfers

## Setup

1. Clone this repository:
```bash
git clone https://github.com/yourusername/solana-volume-bot.git
cd solana-volume-bot
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Create a `.env` file in the project root with the following contents:
```
BOT_TOKEN=your_telegram_bot_token
API_BASE_URL=http://localhost:8000
LOG_LEVEL=INFO
```

Replace `your_telegram_bot_token` with your actual Telegram bot token from [@BotFather](https://t.me/BotFather).

## Running the Bot

From the project directory, run:

```bash
python run_bot.py
```

The bot will start and listen for commands. You can interact with it by opening a Telegram chat with your bot.

## Development

### Project Structure

- `bot/` - Main package
  - `main.py` - Bot initialization and setup
  - `config.py` - Configuration and constants
  - `api/` - API client for backend
  - `events/` - Event system for real-time updates
  - `handlers/` - Telegram command handlers
  - `state/` - State management
  - `utils/` - Utility functions
- `requirements.txt` - Dependencies
- `run_bot.py` - Entry point script

### Adding New Features

1. To add a new command, create a handler in `bot/handlers/` and register it in `bot/main.py`.
2. To add functionality that needs to persist between restarts, update the API client to interact with the backend storage.

## License

MIT 