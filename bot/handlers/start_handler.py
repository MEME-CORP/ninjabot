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

from bot.config import ConversationState, MIN_CHILD_WALLETS, SERVICE_FEE_RATE, CONVERSATION_TIMEOUT
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
    
    # Check if there are any saved mother wallets
    saved_wallets = api_client.list_saved_wallets('mother')
    
    # Build keyboard with wallet options
    keyboard = [
        [build_button("Create New Wallet", "create_wallet")],
        [build_button("Use My Wallet", "import_wallet")]
    ]
    
    # Add option to use existing wallets if available
    if saved_wallets:
        keyboard.append([build_button("Use Saved Wallet", "use_saved_wallet")])
    
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
            session_manager.update_session_value(user.id, "mother_private_key", wallet_info.get("private_key", ""))
            
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
    
    elif choice == "use_saved_wallet":
        # Show list of saved wallets to choose from
        saved_wallets = api_client.list_saved_wallets('mother')
        
        if not saved_wallets:
            # No saved wallets found
            logger.warning(f"No saved wallets found for user {user.id}")
            
            keyboard = [
                [build_button("Create New Wallet", "create_wallet")],
                [build_button("Use My Wallet", "import_wallet")]
            ]
            
            await query.edit_message_text(
                "No saved wallets found. Please create a new wallet or import an existing one.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return ConversationState.WALLET_CHOICE
        
        # Store the wallet data in user's session for reference by index
        wallet_mapping = {}
        for i, wallet in enumerate(saved_wallets):
            # Use simple numeric index as key to avoid long callback data
            wallet_mapping[i] = wallet['address']
        
        # Save the mapping to session for later reference
        session_manager.update_session_value(user.id, "wallet_mapping", wallet_mapping)
        
        # Build keyboard with saved wallet options
        keyboard = []
        for i, wallet in enumerate(saved_wallets):
            # Format wallet address for display (first 8 chars + ... + last 8 chars)
            address = wallet['address']
            short_address = f"{address[:8]}...{address[-8:]}" if len(address) > 16 else address
            
            # Use simple numeric index as callback data to avoid Telegram limits
            keyboard.append([build_button(
                f"Wallet {i+1}: {short_address}",
                f"wallet_{i}"
            )])
        
        # Add back button
        keyboard.append([build_button("« Back", "back_to_wallet_choice")])
        
        await query.edit_message_text(
            "Select a saved wallet:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return ConversationState.SAVED_WALLET_CHOICE
    
    elif choice == "back_to_wallet_choice":
        # Go back to wallet choice
        return await start(update, context)
    
    else:
        # Check if this is a saved wallet selection
        if choice.startswith("wallet_"):
            # Extract wallet index from callback data
            try:
                wallet_index = int(choice.replace("wallet_", ""))
                
                # Get the wallet mapping from session
                wallet_mapping = session_manager.get_session_value(user.id, "wallet_mapping", {})
                
                # Get the full wallet address using the index
                wallet_address = wallet_mapping.get(wallet_index)
                
                if not wallet_address:
                    logger.error(
                        f"Could not find wallet address for index {wallet_index} in user {user.id}'s session",
                        extra={"user_id": user.id, "wallet_index": wallet_index}
                    )
                    
                    # Send error message and go back to wallet choice
                    await query.edit_message_text(
                        format_error_message(f"Could not find wallet. Please try again."),
                        reply_markup=InlineKeyboardMarkup([[build_button("Try Again", "use_saved_wallet")]])
                    )
                    
                    return ConversationState.WALLET_CHOICE
                
                # Load wallet data
                wallet_data = api_client.load_wallet_data('mother', wallet_address)
                
                if not wallet_data:
                    logger.error(
                        f"Could not load saved wallet {wallet_address} for user {user.id}",
                        extra={"user_id": user.id, "wallet": wallet_address}
                    )
                    
                    # Send error message and go back to wallet choice
                    await query.edit_message_text(
                        format_error_message(f"Could not load saved wallet."),
                        reply_markup=InlineKeyboardMarkup([[build_button("Try Again", "use_saved_wallet")]])
                    )
                    
                    return ConversationState.WALLET_CHOICE
                
                # Store wallet data in session
                session_manager.update_session_value(user.id, "mother_wallet", wallet_address)
                session_manager.update_session_value(user.id, "mother_private_key", wallet_data.get("private_key", ""))
                
                logger.info(
                    f"Using saved wallet {wallet_address} for user {user.id}",
                    extra={"user_id": user.id, "wallet": wallet_address}
                )
                
                # Check if there are saved child wallets for this mother wallet
                child_wallets = api_client.load_child_wallets(wallet_address)
                
                # Build keyboard with options
                keyboard = []
                
                if child_wallets:
                    # Option to use existing child wallets
                    keyboard.append([build_button("Use Existing Child Wallets", f"use_existing_children_{wallet_index}")])
                
                # Option to create new child wallets
                keyboard.append([build_button("Create New Child Wallets", f"create_new_children_{wallet_index}")])
                
                # Send confirmation and ask about child wallets
                await query.edit_message_text(
                    f"✅ Using saved wallet: `{wallet_address}`\n\nWhat would you like to do with child wallets?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
                
                return ConversationState.CHILD_WALLET_CHOICE
                
            except (ValueError, TypeError) as e:
                logger.error(f"Error parsing wallet index: {str(e)}", extra={"user_id": user.id, "choice": choice})
                
                # Send error message and go back to wallet choice
                await query.edit_message_text(
                    format_error_message(f"Invalid wallet selection. Please try again."),
                    reply_markup=InlineKeyboardMarkup([[build_button("Try Again", "use_saved_wallet")]])
                )
                
                return ConversationState.WALLET_CHOICE
        
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
        session_manager.update_session_value(user.id, "mother_private_key", private_key)
        
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
        # Show checking message first to provide immediate feedback
        try:
            await query.edit_message_text(
                f"Checking balance for wallet: `{mother_wallet[:8]}...{mother_wallet[-8:]}`...",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as edit_error:
            logger.warning(
                f"Could not update 'checking' message: {str(edit_error)}",
                extra={"user_id": user.id}
            )
        
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
            try:
                await query.edit_message_text(
                    format_sufficient_balance_message(
                        balance=current_balance,
                        token_symbol=token_symbol
                    ),
                    reply_markup=InlineKeyboardMarkup([[
                        build_button("Begin Transfers", "start_execution")
                    ]]),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as edit_error:
                logger.warning(
                    f"Could not update sufficient balance message: {str(edit_error)}",
                    extra={"user_id": user.id, "error": str(edit_error)}
                )
                # If edit fails, send a new message
                await context.bot.send_message(
                    chat_id=user.id,
                    text=format_sufficient_balance_message(
                        balance=current_balance,
                        token_symbol=token_symbol
                    ),
                    reply_markup=InlineKeyboardMarkup([[
                        build_button("Begin Transfers", "start_execution")
                    ]]),
                    parse_mode=ParseMode.MARKDOWN
                )
            
            return ConversationState.AWAIT_FUNDING
        else:
            # Insufficient balance
            try:
                await query.edit_message_text(
                    format_insufficient_balance_message(
                        current_balance=current_balance,
                        required_balance=total_volume,
                        token_symbol=token_symbol
                    ),
                    reply_markup=InlineKeyboardMarkup([[
                        build_button("Check Again", "check_balance")
                    ]]),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as edit_error:
                logger.warning(
                    f"Could not update insufficient balance message: {str(edit_error)}",
                    extra={"user_id": user.id, "error": str(edit_error)}
                )
                # If edit fails, send a new message
                await context.bot.send_message(
                    chat_id=user.id,
                    text=format_insufficient_balance_message(
                        current_balance=current_balance,
                        required_balance=total_volume,
                        token_symbol=token_symbol
                    ),
                    reply_markup=InlineKeyboardMarkup([[
                        build_button("Check Again", "check_balance")
                    ]]),
                    parse_mode=ParseMode.MARKDOWN
                )
            
            return ConversationState.AWAIT_FUNDING
            
    except ApiClientError as e:
        logger.error(
            f"Error checking balance: {str(e)}",
            extra={"user_id": user.id, "wallet": mother_wallet}
        )
        
        # Send error message with retry button
        try:
            await query.edit_message_text(
                format_error_message(f"Could not check balance: {str(e)}"),
                reply_markup=InlineKeyboardMarkup([[
                    build_button("Try Again", "check_balance")
                ]]),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as edit_error:
            # If edit fails, send a new message
            await context.bot.send_message(
                chat_id=user.id,
                text=format_error_message(f"Could not check balance: {str(e)}"),
                reply_markup=InlineKeyboardMarkup([[
                    build_button("Try Again", "check_balance")
                ]]),
                parse_mode=ParseMode.MARKDOWN
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
        # Retrieve necessary wallet data for direct funding approach
        mother_wallet = session_manager.get_session_value(user.id, "mother_wallet")
        mother_private_key = session_manager.get_session_value(user.id, "mother_private_key")
        child_wallets = session_manager.get_session_value(user.id, "child_wallets")
        token_address = session_manager.get_session_value(user.id, "token_address", "So11111111111111111111111111111111111111112")  # Default to SOL
        
        # Calculate amount per wallet from total_volume divided by number of child wallets
        total_volume = session_manager.get_session_value(user.id, "total_volume", 0)
        num_child_wallets = len(child_wallets) if child_wallets else 0
        amount_per_wallet = total_volume / num_child_wallets if num_child_wallets > 0 else 0
        
        # Priority fee for faster transactions (microLamports)
        priority_fee = 25000  # Default priority fee
        
        # Start execution
        result = api_client.start_execution(run_id)
        
        # Check if we need to handle direct funding (API endpoint not available)
        if result.get("status") == "execute_endpoint_not_found":
            logger.info(
                f"Using direct funding approach for user {user.id}",
                extra={"user_id": user.id, "run_id": run_id}
            )
            
            # Check if transfers have already been initiated for this session
            if session_manager.get_session_value(user.id, "transfers_initiated"):
                logger.warning(f"Transfers already initiated for user {user.id} - preventing duplicate execution")
                
                # Send message about duplicate execution attempt
                await context.bot.send_message(
                    chat_id=user.id,
                    text="⚠️ Transfers have already been initiated. Please wait for them to complete."
                )
                
                return ConversationState.EXECUTION
            
            # Verify we have all required data for direct funding
            if not all([mother_wallet, child_wallets, amount_per_wallet > 0]):
                error_msg = "Missing required data for direct wallet funding"
                logger.error(
                    f"{error_msg} for user {user.id}",
                    extra={
                        "user_id": user.id, 
                        "mother_wallet_exists": bool(mother_wallet),
                        "child_wallets_count": len(child_wallets) if child_wallets else 0,
                        "amount_per_wallet": amount_per_wallet
                    }
                )
                
                # Send error message with restart button
                await context.bot.send_message(
                    chat_id=user.id,
                    text=format_error_message(f"{error_msg}. Please restart with /start."),
                    reply_markup=None
                )
                
                return ConversationState.START
            
            # Check if we have the private key for signing transactions
            if not mother_private_key:
                logger.error(
                    f"Missing mother wallet private key for user {user.id}",
                    extra={"user_id": user.id, "mother_wallet": mother_wallet}
                )
                
                # Send error message about missing private key
                await context.bot.send_message(
                    chat_id=user.id,
                    text=format_error_message("Missing mother wallet private key. Please restart with /start and create a new wallet."),
                    reply_markup=None
                )
                
                return ConversationState.START
            
            # Generate a batch ID for this execution
            batch_id = api_client.generate_batch_id()
            
            # Log direct funding attempt
            logger.info(
                f"Starting direct funding with batch ID: {batch_id}",
                extra={
                    "user_id": user.id,
                    "batch_id": batch_id,
                    "mother_wallet": mother_wallet,
                    "child_wallets_count": len(child_wallets),
                    "amount_per_wallet": amount_per_wallet,
                    "has_private_key": bool(mother_private_key),
                    "private_key_length": len(mother_private_key) if mother_private_key else 0
                }
            )
            
            # Implement direct funding approach like in test_specific_transfers.py
            funding_result = api_client.fund_child_wallets(
                mother_wallet=mother_wallet,
                child_wallets=child_wallets,
                token_address=token_address,
                amount_per_wallet=amount_per_wallet,
                mother_private_key=mother_private_key,
                priority_fee=priority_fee,
                batch_id=batch_id
            )
            
            # Update session with batch ID
            session_manager.update_session_value(user.id, "batch_id", batch_id)
            
            # Mark transfers as initiated to prevent duplicates
            session_manager.update_session_value(user.id, "transfers_initiated", True)
            
            # Log the funding result
            logger.info(
                f"Direct funding result for user {user.id}",
                extra={"user_id": user.id, "batch_id": batch_id, "result": funding_result}
            )
        else:
            logger.info(
                f"Started execution using API endpoint for user {user.id}",
                extra={"user_id": user.id, "run_id": run_id, "result": result}
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


async def child_wallet_choice(update: Update, context: CallbackContext) -> int:
    """
    Handle the choice of using existing child wallets or creating new ones.
    
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
    
    # Get mother wallet from session
    mother_wallet = session_manager.get_session_value(user.id, "mother_wallet")
    
    if not mother_wallet:
        logger.error(
            f"No mother wallet found in session for user {user.id}",
            extra={"user_id": user.id}
        )
        
        # Send error message and go back to wallet choice
        await query.edit_message_text(
            format_error_message("Session data lost. Please start again."),
            reply_markup=InlineKeyboardMarkup([[build_button("Start Over", "back_to_wallet_choice")]])
        )
        
        return ConversationState.WALLET_CHOICE
    
    if choice.startswith("use_existing_children_"):
        try:
            # Extract wallet index from callback data
            wallet_index = int(choice.replace("use_existing_children_", ""))
            
            # Get wallet mapping from session to verify the mother wallet
            wallet_mapping = session_manager.get_session_value(user.id, "wallet_mapping", {})
            selected_mother_wallet = wallet_mapping.get(wallet_index)
            
            # Verify the mother address matches the one in session
            if selected_mother_wallet != mother_wallet:
                logger.error(
                    f"Mother wallet mismatch for user {user.id}: {selected_mother_wallet} vs {mother_wallet}",
                    extra={"user_id": user.id}
                )
                
                # Send error message and go back to wallet choice
                await query.edit_message_text(
                    format_error_message("Mother wallet mismatch. Please start again."),
                    reply_markup=InlineKeyboardMarkup([[build_button("Start Over", "back_to_wallet_choice")]])
                )
                
                return ConversationState.WALLET_CHOICE
            
            # Load existing child wallets for this mother wallet
            child_wallets = api_client.load_child_wallets(mother_wallet)
            
            if not child_wallets:
                logger.error(
                    f"No child wallets found for mother wallet {mother_wallet}",
                    extra={"user_id": user.id, "mother_wallet": mother_wallet}
                )
                
                # Send error message and offer to create new child wallets
                await query.edit_message_text(
                    format_error_message("No child wallets found for this mother wallet."),
                    reply_markup=InlineKeyboardMarkup([
                        [build_button("Create New Child Wallets", f"create_new_children_{wallet_index}")]
                    ])
                )
                
                return ConversationState.CHILD_WALLET_CHOICE
            
            # Store child wallets in session
            child_addresses = [wallet.get('address') for wallet in child_wallets if wallet.get('address')]
            session_manager.update_session_value(user.id, "child_wallets", child_addresses)
            
            # Set number of child wallets
            num_wallets = len(child_addresses)
            session_manager.update_session_value(user.id, "num_child_wallets", num_wallets)
            
            logger.info(
                f"Using {num_wallets} existing child wallets for user {user.id}",
                extra={"user_id": user.id, "mother_wallet": mother_wallet, "num_wallets": num_wallets}
            )
            
            # Confirm and ask for volume
            await query.edit_message_text(
                format_child_wallets_message(num_wallets, child_addresses)
            )
            
            return ConversationState.VOLUME_AMOUNT
        except (ValueError, TypeError) as e:
            logger.error(
                f"Error parsing wallet index in child wallet choice: {str(e)}",
                extra={"user_id": user.id, "choice": choice}
            )
            
            # Send error message and go back to wallet choice
            await query.edit_message_text(
                format_error_message("Invalid selection. Please start again."),
                reply_markup=InlineKeyboardMarkup([[build_button("Start Over", "back_to_wallet_choice")]])
            )
            
            return ConversationState.WALLET_CHOICE
    
    elif choice.startswith("create_new_children_"):
        try:
            # Extract wallet index from callback data
            wallet_index = int(choice.replace("create_new_children_", ""))
            
            # Get wallet mapping from session to verify the mother wallet
            wallet_mapping = session_manager.get_session_value(user.id, "wallet_mapping", {})
            selected_mother_wallet = wallet_mapping.get(wallet_index)
            
            # Verify the mother address matches the one in session
            if selected_mother_wallet != mother_wallet:
                logger.error(
                    f"Mother wallet mismatch for user {user.id}: {selected_mother_wallet} vs {mother_wallet}",
                    extra={"user_id": user.id}
                )
                
                # Send error message and go back to wallet choice
                await query.edit_message_text(
                    format_error_message("Mother wallet mismatch. Please start again."),
                    reply_markup=InlineKeyboardMarkup([[build_button("Start Over", "back_to_wallet_choice")]])
                )
                
                return ConversationState.WALLET_CHOICE
            
            # Ask for number of child wallets
            await query.edit_message_text(
                f"How many child wallets would you like to create? (min: {MIN_CHILD_WALLETS})\n\n"
                f"Each child wallet will be used for transfers to simulate trading volume."
            )
            
            return ConversationState.NUM_CHILD_WALLETS
        except (ValueError, TypeError) as e:
            logger.error(
                f"Error parsing wallet index in child wallet choice: {str(e)}",
                extra={"user_id": user.id, "choice": choice}
            )
            
            # Send error message and go back to wallet choice
            await query.edit_message_text(
                format_error_message("Invalid selection. Please start again."),
                reply_markup=InlineKeyboardMarkup([[build_button("Start Over", "back_to_wallet_choice")]])
            )
            
            return ConversationState.WALLET_CHOICE
    
    else:
        # Invalid choice
        logger.warning(
            f"Invalid child wallet choice: {choice}",
            extra={"user_id": user.id}
        )
        
        # Go back to child wallet choice
        await query.edit_message_text(
            "Invalid selection. Please choose an option:",
            reply_markup=InlineKeyboardMarkup([
                [build_button("Create New Child Wallets", f"create_new_children_0")]
            ])
        )
        
        return ConversationState.CHILD_WALLET_CHOICE


def register_start_handler(application):
    """
    Register the start command handler.
    
    Args:
        application: The application to register the handler to
    """
    # Create conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ConversationState.WALLET_CHOICE: [
                CallbackQueryHandler(wallet_choice)
            ],
            ConversationState.IMPORT_WALLET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, import_wallet)
            ],
            ConversationState.SAVED_WALLET_CHOICE: [
                CallbackQueryHandler(wallet_choice)
            ],
            ConversationState.CHILD_WALLET_CHOICE: [
                CallbackQueryHandler(child_wallet_choice)
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
                CallbackQueryHandler(check_balance, pattern=r"^check_balance$"),
                CallbackQueryHandler(regenerate_preview, pattern=r"^regenerate$")
            ],
            ConversationState.AWAIT_FUNDING: [
                CallbackQueryHandler(check_balance, pattern=r"^check_balance$"),
                CallbackQueryHandler(start_execution, pattern=r"^start_execution$")
            ],
            ConversationState.EXECUTION: [
                CallbackQueryHandler(cancel, pattern=r"^cancel$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        name="start_conversation",
        persistent=False
    )
    
    # Register the conversation handler
    application.add_handler(conv_handler) 