"""
Rate Limiting Utilities for User Feedback

This module provides utilities for handling rate limiting with user feedback
across different handlers in the NinjaBot application.
"""

import asyncio
from typing import Optional
from telegram import Update, Bot
from telegram.constants import ParseMode
from loguru import logger


class RateLimitFeedback:
    """
    Provides user feedback and handling for rate limiting scenarios.
    
    This class encapsulates the logic for detecting rate limiting errors
    and providing appropriate user feedback during wait periods.
    """
    
    @staticmethod
    async def handle_rate_limit_error(
        bot: Bot,
        chat_id: int,
        message_id: Optional[int],
        operation_name: str,
        error_message: str,
        estimated_wait_time: int = 60
    ) -> None:
        """
        Handle rate limiting error with user feedback.
        
        Args:
            bot: Telegram bot instance
            chat_id: Chat ID for the message
            message_id: Message ID to edit (if None, sends new message)
            operation_name: Name of the operation being rate limited
            error_message: The rate limiting error message
            estimated_wait_time: Estimated wait time in seconds
        """
        wait_minutes = max(1, estimated_wait_time // 60)
        
        feedback_text = (
            f"⏱️ <b>Rate Limiting Detected</b>\n\n"
            f"The blockchain network is experiencing high traffic during your "
            f"<b>{operation_name}</b> operation.\n\n"
            f"⏰ <b>Automatic Retry:</b> ~{wait_minutes} minute(s)\n"
            f"🔄 <b>Status:</b> Retrying with intelligent backoff\n\n"
            f"💡 <i>This helps prevent network congestion and ensures successful transactions.</i>\n\n"
            f"🎯 <b>Your operation will complete automatically.</b> Please wait..."
        )
        
        try:
            if message_id:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=feedback_text,
                    parse_mode=ParseMode.HTML
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=feedback_text,
                    parse_mode=ParseMode.HTML
                )
                
            logger.info(f"Rate limit feedback sent to user in chat {chat_id} for operation: {operation_name}")
            
        except Exception as e:
            logger.error(f"Failed to send rate limit feedback: {e}")
    
    @staticmethod
    async def send_retry_progress(
        bot: Bot,
        chat_id: int,
        message_id: Optional[int],
        operation_name: str,
        attempt_number: int,
        max_attempts: int,
        next_retry_seconds: int
    ) -> None:
        """
        Send progress update during retry attempts.
        
        Args:
            bot: Telegram bot instance
            chat_id: Chat ID for the message
            message_id: Message ID to edit
            operation_name: Name of the operation being retried
            attempt_number: Current attempt number
            max_attempts: Maximum number of attempts
            next_retry_seconds: Seconds until next retry
        """
        progress_text = (
            f"🔄 <b>Retrying {operation_name}</b>\n\n"
            f"📊 <b>Attempt:</b> {attempt_number}/{max_attempts}\n"
            f"⏰ <b>Next retry:</b> {next_retry_seconds}s\n\n"
            f"🌐 <i>Network traffic is high, please be patient...</i>"
        )
        
        try:
            if message_id:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=progress_text,
                    parse_mode=ParseMode.HTML
                )
                
            logger.debug(f"Retry progress update sent for {operation_name}: attempt {attempt_number}/{max_attempts}")
            
        except Exception as e:
            logger.error(f"Failed to send retry progress update: {e}")
    
    @staticmethod
    def is_rate_limit_error(error_message: str) -> bool:
        """
        Check if an error message indicates rate limiting.
        
        Args:
            error_message: The error message to check
            
        Returns:
            True if this appears to be a rate limiting error
        """
        rate_limit_indicators = [
            "Failed to send Jito bundle",
            "rate limit",
            "too many requests", 
            "429",
            "throttle",
            "jito.wtf/api/v1/bundles",
            "bundle submission failed"
        ]
        
        error_lower = error_message.lower()
        for indicator in rate_limit_indicators:
            if indicator.lower() in error_lower:
                return True
        return False
    
    @staticmethod
    async def handle_operation_with_rate_limit_feedback(
        operation_func,
        bot: Bot,
        chat_id: int,
        message_id: Optional[int],
        operation_name: str,
        *args,
        **kwargs
    ):
        """
        Execute an operation with automatic rate limiting feedback.
        
        Args:
            operation_func: The function to execute
            bot: Telegram bot instance
            chat_id: Chat ID for feedback messages
            message_id: Message ID to edit
            operation_name: Human-readable name for the operation
            *args, **kwargs: Arguments passed to operation_func
            
        Returns:
            Result of operation_func
            
        Raises:
            Re-raises any non-rate-limiting exceptions
        """
        try:
            return await operation_func(*args, **kwargs) if asyncio.iscoroutinefunction(operation_func) else operation_func(*args, **kwargs)
            
        except Exception as e:
            if RateLimitFeedback.is_rate_limit_error(str(e)):
                await RateLimitFeedback.handle_rate_limit_error(
                    bot=bot,
                    chat_id=chat_id,
                    message_id=message_id,
                    operation_name=operation_name,
                    error_message=str(e)
                )
                # Re-raise to let the underlying retry logic handle it
                raise e
            else:
                # Not a rate limiting error, re-raise as-is
                raise e
