#!/usr/bin/env python
"""
Run script for the Solana Volume Telegram Bot.

This script sets up logging directories and runs the bot.
"""

import os
import sys
import asyncio
from pathlib import Path

# Ensure 'bot' directory is in the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Create logs directory if it doesn't exist
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

# Import the bot's main function after setting up paths
from bot.main import main

if __name__ == "__main__":
    asyncio.run(main()) 