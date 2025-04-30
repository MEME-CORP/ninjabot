#!/usr/bin/env python
import os
import logging
import asyncio
from dotenv import load_dotenv
from loguru import logger
from telegram.ext import ApplicationBuilder, CommandHandler

from bot.handlers.start_handler import register_start_handler
from bot.config import BOT_TOKEN, LOG_LEVEL
from bot.events.event_system import event_system

def setup_logging():
    """Configure structured logging with loguru."""
    logger.remove()  # Remove default handler
    logger.add(
        "logs/bot_{time}.log",
        rotation="1 day",
        retention="14 days",
        level=LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message} | {extra}",
        serialize=True,  # JSON formatting for structured logs
    )
    
    # Also send logs to stdout
    logger.add(
        lambda msg: print(msg, end=""),
        level=LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    )
    
    # Redirect telegram logger to loguru
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

class InterceptHandler(logging.Handler):
    """Intercept standard logging and redirect to loguru."""
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
            
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
            
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

async def main():
    """Initialize and start the bot."""
    # Setup logging first for observability
    setup_logging()
    
    logger.info("Starting Solana Volume Telegram Bot")
    
    # Create the Application and pass it your bot's token
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Start the event system
    await event_system.start()
    
    # Register command handlers
    register_start_handler(application)
    
    # Add error handler for graceful fallbacks
    application.add_error_handler(error_handler)
    
    # Start the Bot
    logger.info("Bot is starting polling")
    await application.initialize()
    await application.start_polling()
    
    # Block until the user presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT
    await application.idle()
    
    # Shutdown the event system
    await event_system.stop()
    
async def error_handler(update, context):
    """Log errors and send a user-friendly message."""
    logger.error(
        f"Update {update} caused error {context.error}",
        extra={"update_id": update.update_id if update else None}
    )
    
    # Send message to the user
    if update and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Sorry, something went wrong. Please try again or restart with /start."
        )

if __name__ == '__main__':
    asyncio.run(main()) 