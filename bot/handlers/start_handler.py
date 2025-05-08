from typing import Dict, List, Any, Optional
import asyncio
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackContext, 
    CommandHandler, 
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from loguru import logger

from bot.config import ConversationState, MIN_CHILD_WALLETS, SERVICE_FEE_RATE
from bot.utils.keyboard_utils import build_button, build_keyboard, build_menu
from bot.utils.validation_utils import (
    validate_child_wallets_input, 
    validate_volume_input,
    validate_token_address,
    validate_wallet_address,
    log_validation_result
)
from bot.utils.message_utils import (
    format_welcome_message,
    format_wallet_created_message,
    format_wallet_imported_message,
    format_child_wallets_message,
    format_volume_confirmation_message,
    format_schedule_preview,
    format_insufficient_balance_message,
    format_sufficient_balance_message,
    format_transaction_status_message,
    format_error_message
)
from bot.api.api_client import api_client, ApiClientError
from bot.events.event_system import event_system
from bot.utils.balance_poller import balance_poller
from bot.state.session_manager import session_manager


# Handler functions
async def start(update: Update, context: CallbackContext) -> int:
    """
    Start the conversation and ask for wallet creation or import.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.effective_user
    logger.info(
        f"User {user.id} started the bot",
        extra={"user_id": user.id, "username": user.username}
    )
    
    # Clear any existing session data
    session_manager.clear_session(user.id)
    
    # Build keyboard with wallet options
    keyboard = [
        [build_button("Create New Wallet", "create_wallet")],
        [build_button("Use My Wallet", "import_wallet")]
    ]
    
    # Send welcome message with keyboard
    await update.message.reply_text(
        format_welcome_message(),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.WALLET_CHOICE


async def wallet_choice(update: Update, context: CallbackContext) -> int:
    """
    Handle wallet creation or import choice.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    
    if choice == "create_wallet":
        # Create a new wallet
        try:
            wallet_info = api_client.create_wallet()
            address = wallet_info["address"]
            
            # Store in session
            session_manager.update_session_value(user.id, "mother_wallet", address)
            
            logger.info(
                f"Created wallet for user {user.id}",
                extra={"user_id": user.id, "wallet": address}
            )
            
            # Send confirmation and ask for number of child wallets
            await query.edit_message_text(
                format_wallet_created_message(address),
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.NUM_CHILD_WALLETS
            
        except ApiClientError as e:
            logger.error(
                f"Error creating wallet: {str(e)}",
                extra={"user_id": user.id}
            )
            
            # Send error message with retry button
            keyboard = [[build_button("Try Again", "create_wallet")]]
            
            await query.edit_message_text(
                format_error_message(f"Could not create wallet: {str(e)}"),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return ConversationState.WALLET_CHOICE
    
    elif choice == "import_wallet":
        # Ask for private key
        await query.edit_message_text(
            "Please enter your wallet private key:"
        )
        
        return ConversationState.IMPORT_WALLET
    
    else:
        # Invalid choice
        logger.warning(
            f"Invalid wallet choice: {choice}",
            extra={"user_id": user.id}
        )
        
        # Return to start
        await start(update, context)
        return ConversationState.WALLET_CHOICE


async def import_wallet(update: Update, context: CallbackContext) -> int:
    """
    Import a wallet using a private key.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.effective_user
    private_key = update.message.text
    
    # Delete the message containing the private key for security
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(
            f"Could not delete private key message: {str(e)}",
            extra={"user_id": user.id}
        )
    
    try:
        # Import the wallet
        wallet_info = api_client.import_wallet(private_key)
        address = wallet_info["address"]
        
        # Store in session
        session_manager.update_session_value(user.id, "mother_wallet", address)
        
        logger.info(
            f"Imported wallet for user {user.id}",
            extra={"user_id": user.id, "wallet": address}
        )
        
        # Send confirmation and ask for number of child wallets
        await context.bot.send_message(
            chat_id=user.id,
            text=format_wallet_imported_message(address),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.NUM_CHILD_WALLETS
        
    except ApiClientError as e:
        logger.error(
            f"Error importing wallet: {str(e)}",
            extra={"user_id": user.id}
        )
        
        # Send error message with retry button
        keyboard = [
            [build_button("Try Again", "import_wallet")],
            [build_button("Create New Wallet", "create_wallet")]
        ]
        
        await context.bot.send_message(
            chat_id=user.id,
            text=format_error_message(f"Could not import wallet: {str(e)}"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return ConversationState.WALLET_CHOICE


async def num_child_wallets(update: Update, context: CallbackContext) -> int:
    """
    Handle the number of child wallets input.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.effective_user
    
    # Get the input text from either message or callback
    if update.message:
        text = update.message.text
    else:
        # If from callback (retry), use the callback data
        query = update.callback_query
        await query.answer()
        text = query.data.replace("retry_wallets_", "")
    
    # Validate input
    is_valid, value_or_error = validate_child_wallets_input(text)
    log_validation_result(user.id, "child_wallets", is_valid, value_or_error)
    
    if not is_valid:
        # Invalid input, send error and ask again
        keyboard = [[build_button(f"Use minimum ({MIN_CHILD_WALLETS})", f"retry_wallets_{MIN_CHILD_WALLETS}")]]
        
        if update.message:
            await update.message.reply_text(
                format_error_message(value_or_error),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                format_error_message(value_or_error),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        return ConversationState.NUM_CHILD_WALLETS
    
    # Valid input, store and continue
    num_wallets = value_or_error
    session_manager.update_session_value(user.id, "num_child_wallets", num_wallets)
    
    logger.info(
        f"User {user.id} selected {num_wallets} child wallets",
        extra={"user_id": user.id, "num_wallets": num_wallets}
    )
    
    # Fetch mother wallet from session
    mother_wallet = session_manager.get_session_value(user.id, "mother_wallet")
    
    try:
        # Create child wallets - api_client now returns a normalized format with wallet objects
        # that always have an 'address' property
        child_wallets_response = api_client.derive_child_wallets(num_wallets, mother_wallet)
        
        # Extract child wallet addresses - should be simpler now with improved api_client
        child_addresses = []
        
        # Process the normalized response from api_client
        for wallet in child_wallets_response:
            if isinstance(wallet, dict) and "address" in wallet:
                child_addresses.append(wallet["address"])
        
        # Ensure we have the expected number of addresses
        if len(child_addresses) != num_wallets:
            logger.warning(
                f"Expected {num_wallets} child wallets but got {len(child_addresses)}",
                extra={"user_id": user.id}
            )
        
        session_manager.update_session_value(user.id, "child_wallets", child_addresses)
        
        logger.info(
            f"Created {len(child_addresses)} child wallets for user {user.id}",
            extra={"user_id": user.id, "mother_wallet": mother_wallet}
        )
        
        # Confirm and ask for volume
        if update.message:
            await update.message.reply_text(format_child_wallets_message(num_wallets, child_addresses))
        else:
            await query.edit_message_text(format_child_wallets_message(num_wallets, child_addresses))
            
        return ConversationState.VOLUME_AMOUNT
        
    except ApiClientError as e:
        logger.error(
            f"Error creating child wallets: {str(e)}",
            extra={"user_id": user.id, "mother_wallet": mother_wallet}
        )
        
        # Send error message with retry button
        keyboard = [[build_button("Try Again", f"retry_wallets_{num_wallets}")]]
        
        if update.message:
            await update.message.reply_text(
                format_error_message(f"Could not create child wallets: {str(e)}"),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                format_error_message(f"Could not create child wallets: {str(e)}"),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        return ConversationState.NUM_CHILD_WALLETS


async def volume_amount(update: Update, context: CallbackContext) -> int:
    """
    Handle the volume amount input.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.effective_user
    text = update.message.text
    
    # Validate input
    is_valid, value_or_error = validate_volume_input(text)
    log_validation_result(user.id, "volume", is_valid, value_or_error)
    
    if not is_valid:
        # Invalid input, send error and ask again
        await update.message.reply_text(format_error_message(value_or_error))
        return ConversationState.VOLUME_AMOUNT
    
    # Valid input, store and continue
    volume = value_or_error
    session_manager.update_session_value(user.id, "total_volume", volume)
    
    logger.info(
        f"User {user.id} set volume to {volume}",
        extra={"user_id": user.id, "volume": volume}
    )
    
    # Ask for token address
    await update.message.reply_text(format_volume_confirmation_message(volume))
    
    return ConversationState.TOKEN_ADDRESS


async def token_address(update: Update, context: CallbackContext) -> int:
    """
    Handle the token address input.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.effective_user
    text = update.message.text
    
    # Validate input
    is_valid, value_or_error = validate_token_address(text)
    log_validation_result(user.id, "token_address", is_valid, value_or_error)
    
    if not is_valid:
        # Invalid input, send error and ask again
        await update.message.reply_text(format_error_message(value_or_error))
        return ConversationState.TOKEN_ADDRESS
    
    # Valid input, store and continue
    token_address = value_or_error
    session_manager.update_session_value(user.id, "token_address", token_address)
    
    logger.info(
        f"User {user.id} set token address to {token_address}",
        extra={"user_id": user.id, "token_address": token_address}
    )
    
    # Prepare and show schedule preview
    await generate_preview(update, context)
    
    return ConversationState.PREVIEW_SCHEDULE


async def generate_preview(update: Update, context: CallbackContext) -> None:
    """
    Generate and show the schedule preview.
    
    Args:
        update: The update object
        context: The context object
    """
    user = update.effective_user
    
    # Get session data
    mother_wallet = session_manager.get_session_value(user.id, "mother_wallet")
    child_wallets = session_manager.get_session_value(user.id, "child_wallets")
    token_address = session_manager.get_session_value(user.id, "token_address")
    total_volume = session_manager.get_session_value(user.id, "total_volume")
    num_child_wallets = session_manager.get_session_value(user.id, "num_child_wallets")
    
    # Show loading message
    message = await context.bot.send_message(
        chat_id=user.id,
        text="Generating transfer schedule..."
    )
    
    try:
        # Generate schedule
        schedule = api_client.generate_schedule(
            mother_wallet=mother_wallet,
            child_wallets=child_wallets,
            token_address=token_address,
            total_volume=total_volume
        )
        
        # Store schedule in session
        session_manager.update_session_value(user.id, "schedule", schedule)
        session_manager.update_session_value(user.id, "run_id", schedule.get("run_id"))
        
        logger.info(
            f"Generated schedule for user {user.id}",
            extra={
                "user_id": user.id,
                "run_id": schedule.get("run_id"),
                "num_transfers": len(schedule.get("transfers", []))
            }
        )
        
        # Format and show preview
        preview_text = format_schedule_preview(
            schedule=schedule.get("transfers", []),
            total_volume=total_volume,
            token_address=token_address,
            num_child_wallets=num_child_wallets
        )
        
        await message.edit_text(
            preview_text,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Add "wait for funding" message
        await context.bot.send_message(
            chat_id=user.id,
            text="Please fund the wallet now. I'll check the balance every few seconds.",
            reply_markup=InlineKeyboardMarkup([[
                build_button("Check Balance Now", "check_balance")
            ]])
        )
        
        # Start balance polling
        await start_balance_polling(user.id, context)
        
    except ApiClientError as e:
        logger.error(
            f"Error generating schedule: {str(e)}",
            extra={"user_id": user.id}
        )
        
        # Send error message with retry button
        await message.edit_text(
            format_error_message(f"Could not generate schedule: {str(e)}"),
            reply_markup=InlineKeyboardMarkup([[
                build_button("Try Again", "regenerate_preview")
            ]])
        )


async def start_balance_polling(user_id: int, context: CallbackContext) -> None:
    """
    Start polling for wallet balance.
    
    Args:
        user_id: Telegram user ID
        context: Telegram context object
    """
    # Get session data
    mother_wallet = session_manager.get_session_value(user_id, "mother_wallet")
    token_address = session_manager.get_session_value(user_id, "token_address")
    total_volume = session_manager.get_session_value(user_id, "total_volume")
    
    if not all([mother_wallet, token_address, total_volume]):
        logger.error(
            f"Missing session data for balance polling",
            extra={"user_id": user_id}
        )
        return
    
    # Define callback for when target balance is reached
    async def on_target_reached():
        # Update UI to show sufficient balance
        balance_info = api_client.check_balance(mother_wallet, token_address)
        
        # Extract current balance for SOL token
        current_balance = 0
        token_symbol = "tokens"
        
        if isinstance(balance_info, dict) and 'balances' in balance_info:
            for token_balance in balance_info['balances']:
                if token_balance.get('token') == "So11111111111111111111111111111111111111112" or token_balance.get('symbol') == "SOL":
                    current_balance = token_balance.get('amount', 0)
                    token_symbol = token_balance.get('symbol', "SOL")
                    break
        
        await context.bot.send_message(
            chat_id=user_id,
            text=format_sufficient_balance_message(
                balance=current_balance, 
                token_symbol=token_symbol
            ),
            reply_markup=InlineKeyboardMarkup([[
                build_button("Begin Transfers", "start_execution")
            ]])
        )
    
    # Start polling
    await balance_poller.start_polling(
        wallet_address=mother_wallet,
        token_address=token_address,
        target_balance=total_volume,
        on_target_reached=on_target_reached
    )
    
    logger.info(
        f"Started balance polling for user {user_id}",
        extra={"user_id": user_id, "wallet": mother_wallet, "target": total_volume}
    )


async def check_balance(update: Update, context: CallbackContext) -> int:
    """
    Check the balance of the mother wallet.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Get session data
    mother_wallet = session_manager.get_session_value(user.id, "mother_wallet")
    token_address = session_manager.get_session_value(user.id, "token_address")
    total_volume = session_manager.get_session_value(user.id, "total_volume")
    
    if not all([mother_wallet, token_address, total_volume]):
        logger.error(
            f"Missing session data for balance check",
            extra={"user_id": user.id}
        )
        
        await query.edit_message_text(
            format_error_message("Session data missing. Please restart with /start."),
            reply_markup=None
        )
        
        return ConversationState.START
    
    try:
        # Check balance
        balance_info = api_client.check_balance(mother_wallet, token_address)
        
        # Extract current balance for SOL token
        current_balance = 0
        token_symbol = "tokens"
        
        if isinstance(balance_info, dict) and 'balances' in balance_info:
            for token_balance in balance_info['balances']:
                if token_balance.get('token') == "So11111111111111111111111111111111111111112" or token_balance.get('symbol') == "SOL":
                    current_balance = token_balance.get('amount', 0)
                    token_symbol = token_balance.get('symbol', "SOL")
                    break
        
        logger.info(
            f"Checked balance for user {user.id}",
            extra={
                "user_id": user.id,
                "wallet": mother_wallet,
                "balance": current_balance,
                "token_symbol": token_symbol,
                "target": total_volume
            }
        )
        
        # Check if sufficient
        if current_balance >= total_volume:
            # Sufficient balance
            await query.edit_message_text(
                format_sufficient_balance_message(
                    balance=current_balance,
                    token_symbol=token_symbol
                ),
                reply_markup=InlineKeyboardMarkup([[
                    build_button("Begin Transfers", "start_execution")
                ]])
            )
            
            return ConversationState.AWAIT_FUNDING
        else:
            # Insufficient balance
            await query.edit_message_text(
                format_insufficient_balance_message(
                    current_balance=current_balance,
                    required_balance=total_volume,
                    token_symbol=token_symbol
                ),
                reply_markup=InlineKeyboardMarkup([[
                    build_button("Check Again", "check_balance")
                ]])
            )
            
            return ConversationState.AWAIT_FUNDING
            
    except ApiClientError as e:
        logger.error(
            f"Error checking balance: {str(e)}",
            extra={"user_id": user.id, "wallet": mother_wallet}
        )
        
        # Send error message with retry button
        await query.edit_message_text(
            format_error_message(f"Could not check balance: {str(e)}"),
            reply_markup=InlineKeyboardMarkup([[
                build_button("Try Again", "check_balance")
            ]])
        )
        
        return ConversationState.AWAIT_FUNDING


async def start_execution(update: Update, context: CallbackContext) -> int:
    """
    Start executing the transfer schedule.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    # Get session data
    run_id = session_manager.get_session_value(user.id, "run_id")
    schedule = session_manager.get_session_value(user.id, "schedule")
    
    if not run_id or not schedule:
        logger.error(
            f"Missing run_id or schedule for execution",
            extra={"user_id": user.id}
        )
        
        await query.edit_message_text(
            format_error_message("Session data missing. Please restart with /start."),
            reply_markup=None
        )
        
        return ConversationState.START
    
    # Update UI
    await query.edit_message_text(
        "Starting transfer execution...",
        reply_markup=None
    )
    
    try:
        # Start execution
        api_client.start_execution(run_id)
        
        logger.info(
            f"Started execution for user {user.id}",
            extra={"user_id": user.id, "run_id": run_id}
        )
        
        # Register event handler for transaction events
        await setup_transaction_event_handlers(user.id, context)
        
        # Send status message
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                "💫 Volume generation has begun!\n\n"
                "You'll receive updates as transfers are processed.\n"
                "This may take some time depending on the number of transfers."
            )
        )
        
        # For testing/demo, simulate events
        asyncio.create_task(event_system.simulate_events_for_run(run_id, schedule))
        
        return ConversationState.EXECUTION
        
    except ApiClientError as e:
        logger.error(
            f"Error starting execution: {str(e)}",
            extra={"user_id": user.id, "run_id": run_id}
        )
        
        # Send error message with retry button
        await context.bot.send_message(
            chat_id=user.id,
            text=format_error_message(f"Could not start execution: {str(e)}"),
            reply_markup=InlineKeyboardMarkup([[
                build_button("Try Again", "start_execution")
            ]])
        )
        
        return ConversationState.AWAIT_FUNDING


async def setup_transaction_event_handlers(user_id: int, context: CallbackContext) -> None:
    """
    Set up event handlers for transaction events.
    
    Args:
        user_id: Telegram user ID
        context: Telegram context object
    """
    # Handler for transaction sent events
    async def handle_tx_sent(event):
        await context.bot.send_message(
            chat_id=user_id,
            text=format_transaction_status_message(
                tx_hash=event.data["tx_hash"],
                status="Sent",
                from_address=event.data["from"],
                to_address=event.data["to"],
                amount=event.data["amount"],
                token_symbol=event.data.get("token_symbol", "tokens")
            )
        )
    
    # Handler for transaction confirmed events
    async def handle_tx_confirmed(event):
        await context.bot.send_message(
            chat_id=user_id,
            text=format_transaction_status_message(
                tx_hash=event.data["tx_hash"],
                status="Confirmed",
                from_address=event.data["from"],
                to_address=event.data["to"],
                amount=event.data["amount"],
                token_symbol=event.data.get("token_symbol", "tokens")
            )
        )
    
    # Handler for transaction failed events
    async def handle_tx_failed(event):
        await context.bot.send_message(
            chat_id=user_id,
            text=format_transaction_status_message(
                tx_hash=event.data["tx_hash"],
                status="Failed",
                from_address=event.data["from"],
                to_address=event.data["to"],
                amount=event.data["amount"],
                token_symbol=event.data.get("token_symbol", "tokens")
            ) + f"\nError: {event.data.get('error', 'Unknown error')}"
        )
    
    # Handler for transaction retry events
    async def handle_tx_retry(event):
        await context.bot.send_message(
            chat_id=user_id,
            text=format_transaction_status_message(
                tx_hash=event.data["tx_hash"],
                status=f"Retrying (attempt {event.data['retry_count']})",
                from_address=event.data["from"],
                to_address=event.data["to"],
                amount=event.data["amount"],
                token_symbol=event.data.get("token_symbol", "tokens")
            )
        )
    
    # Subscribe to events
    await event_system.start()
    await event_system.subscribe("transaction_sent", handle_tx_sent)
    await event_system.subscribe("transaction_confirmed", handle_tx_confirmed)
    await event_system.subscribe("transaction_failed", handle_tx_failed)
    await event_system.subscribe("transaction_retry", handle_tx_retry)


async def cancel(update: Update, context: CallbackContext) -> int:
    """
    Cancel the conversation and clean up.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        ConversationHandler.END
    """
    user = update.effective_user
    logger.info(f"User {user.id} canceled the conversation")
    
    # Clean up resources
    await balance_poller.stop_all()
    session_manager.clear_session(user.id)
    
    # Send confirmation message
    await update.message.reply_text(
        "Operation cancelled. Type /start to begin again."
    )
    
    return ConversationHandler.END


async def timeout(update: Update, context: CallbackContext) -> int:
    """
    Handle conversation timeout.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        ConversationHandler.END
    """
    user = update.effective_user
    logger.info(f"Conversation with user {user.id} timed out")
    
    # Clean up resources
    await balance_poller.stop_all()
    session_manager.clear_session(user.id)
    
    # Send timeout message
    await update.message.reply_text(
        "The conversation timed out due to inactivity. Type /start to begin again."
    )
    
    return ConversationHandler.END


async def regenerate_preview(update: Update, context: CallbackContext) -> int:
    """
    Regenerate schedule preview.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    query = update.callback_query
    await query.answer()
    
    # Regenerate preview
    await generate_preview(update, context)
    
    return ConversationState.PREVIEW_SCHEDULE


def register_start_handler(application):
    """
    Register the conversation handler for the /start command.
    
    Args:
        application: The Telegram application
    """
    # Define conversation handler with states
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ConversationState.START: [
                CommandHandler("start", start)
            ],
            ConversationState.WALLET_CHOICE: [
                CallbackQueryHandler(wallet_choice)
            ],
            ConversationState.IMPORT_WALLET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, import_wallet)
            ],
            ConversationState.NUM_CHILD_WALLETS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, num_child_wallets),
                CallbackQueryHandler(num_child_wallets, pattern=r"^retry_wallets_")
            ],
            ConversationState.VOLUME_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, volume_amount)
            ],
            ConversationState.TOKEN_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, token_address)
            ],
            ConversationState.PREVIEW_SCHEDULE: [
                CallbackQueryHandler(regenerate_preview, pattern=r"^regenerate_preview$"),
                CallbackQueryHandler(check_balance, pattern=r"^check_balance$")
            ],
            ConversationState.AWAIT_FUNDING: [
                CallbackQueryHandler(check_balance, pattern=r"^check_balance$"),
                CallbackQueryHandler(start_execution, pattern=r"^start_execution$")
            ],
            ConversationState.EXECUTION: [
                # No handlers needed, just event subscribers
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        # Set conversation timeout
        conversation_timeout=1800  # 30 minutes
    )
    
    # Register the conversation handler
    application.add_handler(conv_handler) 