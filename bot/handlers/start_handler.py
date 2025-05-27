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
    format_error_message,
    format_child_balances_overview,
    format_return_funds_summary,
    format_child_wallets_funding_status,
    format_return_funds_progress
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
        [build_button("Use External Wallet", "import_wallet")]
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
                
                # Store child wallets in session
                child_addresses = [wallet.get('address') for wallet in child_wallets if wallet.get('address')]
                session_manager.update_session_value(user.id, "child_wallets", child_addresses)
                
                # Also store the full child wallets data (with private keys) for return funds functionality
                session_manager.update_session_value(user.id, "child_wallets_data", child_wallets)
                
                # Set number of child wallets
                num_wallets = len(child_addresses)
                session_manager.update_session_value(user.id, "num_child_wallets", num_wallets)
                
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
        
        # Extract child wallet addresses and store full wallet data
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
        
        # Store both the full wallet data (with private keys) and just the addresses
        # Full data is needed for fund return functionality
        session_manager.update_session_value(user.id, "child_wallets_data", child_wallets_response)
        # Addresses list for backward compatibility with existing code
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
            num_child_wallets=num_child_wallets,
            mother_wallet_address=mother_wallet
        )
        
        await message.edit_text(
            preview_text,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # BEFORE starting mother wallet balance polling, check if child wallets are already funded
        await context.bot.send_message(
            chat_id=user.id,
            text="🔍 Checking if child wallets are already funded..."
        )
        
        # Calculate amount per child wallet
        amount_per_wallet = total_volume / len(child_wallets) if child_wallets else 0
        
        # Check child wallet funding status
        funding_status = await check_child_wallets_funding_status(user.id, amount_per_wallet)
        
        if funding_status.get("error"):
            # Error checking funding status, inform user but continue with mother wallet check as fallback
            logger.warning(f"Error checking child wallet funding status for user {user.id}: {funding_status['error']}")
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    "⚠️ Could not verify child wallet balances.\n\n"
                    "Proceeding with mother wallet funding check as a safety measure. "
                    "This ensures all wallets will have sufficient funds."
                )
            )
            # Set funding needed as fallback
            session_manager.update_session_value(user.id, "child_wallets_need_funding", True)
        elif funding_status.get("all_funded", False):
            # All child wallets are already funded - show this information to the user
            logger.info(f"All child wallets already sufficiently funded for user {user.id}")
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    f"✅ Child wallets are already funded!\n\n"
                    f"Found {funding_status['funded_wallets']}/{funding_status['total_wallets']} "
                    f"wallets with sufficient balance ({amount_per_wallet:.4f} SOL each).\n\n"
                    f"You can proceed directly to volume generation without additional funding."
                )
            )
            
            # Mark that funding is not needed
            session_manager.update_session_value(user.id, "child_wallets_need_funding", False)
        else:
            # Some or all wallets need funding
            funded_count = funding_status.get("funded_wallets", 0)
            total_count = funding_status.get("total_wallets", 0)
            
            if funded_count > 0:
                logger.info(f"Partial funding needed for user {user.id}: {funded_count}/{total_count} wallets already funded")
                await context.bot.send_message(
                    chat_id=user.id,
                    text=(
                        f"📊 Child Wallet Status: {funded_count}/{total_count} already funded\n\n"
                        f"Some child wallets need funding ({amount_per_wallet:.4f} SOL each).\n"
                        f"Please fund the mother wallet to transfer to remaining child wallets."
                    )
                )
            else:
                logger.info(f"All child wallets need funding for user {user.id}")
                await context.bot.send_message(
                    chat_id=user.id,
                    text=(
                        f"📊 Child Wallet Status: 0/{total_count} funded\n\n"
                        f"Child wallets need funding ({amount_per_wallet:.4f} SOL each).\n"
                        f"Please fund the mother wallet to transfer to child wallets."
                    )
                )
            
            # Mark that funding is needed
            session_manager.update_session_value(user.id, "child_wallets_need_funding", True)
        
        # Store the funding status for later use
        session_manager.update_session_value(user.id, "child_funding_status", funding_status)
        
        # Decision point: Skip mother wallet check if child wallets are already funded
        if funding_status.get("all_funded", False):
            # Child wallets are fully funded - skip mother wallet balance check entirely
            logger.info(f"Child wallets fully funded for user {user.id} - skipping mother wallet balance check")
            logger.info(f"User {user.id} will be in PREVIEW_SCHEDULE state when Return All Funds button is shown")
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    "🚀 Ready to start volume generation!\n\n"
                    "Since your child wallets already have sufficient balance, "
                    "you can proceed directly to volume generation."
                ),
                reply_markup=InlineKeyboardMarkup([
                    [build_button("🚀 Start Volume Generation", "start_execution")],
                    [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")]
                ])
            )
            return  # Exit early - no need for mother wallet balance polling
        
        # Child wallets need funding - proceed with mother wallet balance check
        logger.info(f"Child wallets need funding for user {user.id} - checking mother wallet balance")
        
        # Add "wait for funding" message
        await context.bot.send_message(
            chat_id=user.id,
            text="Please fund the mother wallet now. I'll check the balance every few seconds.",
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
            reply_markup=InlineKeyboardMarkup([
                [build_button("Begin Transfers", "start_execution")],
                [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")]
            ]),
            parse_mode=ParseMode.MARKDOWN
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
                    reply_markup=InlineKeyboardMarkup([
                        [build_button("Begin Transfers", "start_execution")],
                        [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")]
                    ]),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as edit_error:
                logger.warning(
                    f"Could not update sufficient balance message: {str(edit_error)}",
                    extra={"user_id": user.id, "error": str(edit_error)}
                )
                # If edit fails, send a new message
                await context.bot.send_message(
                    chat_id=user_id,
                    text=format_sufficient_balance_message(
                        balance=current_balance,
                        token_symbol=token_symbol
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [build_button("Begin Transfers", "start_execution")],
                        [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")]
                    ]),
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
                    reply_markup=InlineKeyboardMarkup([
                        [build_button("Check Again", "check_balance")],
                        [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")]
                    ]),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as edit_error:
                logger.warning(
                    f"Could not update insufficient balance message: {str(edit_error)}",
                    extra={"user_id": user.id, "error": str(edit_error)}
                )
                # If edit fails, send a new message
                await context.bot.send_message(
                    chat_id=user_id,
                    text=format_insufficient_balance_message(
                        current_balance=current_balance,
                        required_balance=total_volume,
                        token_symbol=token_symbol
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [build_button("Check Again", "check_balance")],
                        [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")]
                    ]),
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
                chat_id=user_id,
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
        # Retrieve necessary wallet data for funding check and potential funding
        mother_wallet = session_manager.get_session_value(user.id, "mother_wallet")
        mother_private_key = session_manager.get_session_value(user.id, "mother_private_key")
        child_wallets = session_manager.get_session_value(user.id, "child_wallets")
        token_address = session_manager.get_session_value(user.id, "token_address", "So11111111111111111111111111111111111111112")  # Default to SOL
        
        # Calculate amount per wallet from total_volume divided by number of child wallets
        total_volume = session_manager.get_session_value(user.id, "total_volume", 0)
        num_child_wallets = len(child_wallets) if child_wallets else 0
        amount_per_wallet = total_volume / num_child_wallets if num_child_wallets > 0 else 0
        
        # Use pre-computed child wallet funding status from generate_preview
        child_wallets_need_funding = session_manager.get_session_value(user.id, "child_wallets_need_funding", True)  # Default to True for safety
        funding_status = session_manager.get_session_value(user.id, "child_funding_status", {})
        
        # Inform user about child wallet funding status
        if not child_wallets_need_funding:
            logger.info(f"Child wallets already sufficiently funded for user {user.id} - skipping funding")
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    f"✅ Child wallets already have sufficient balance!\n\n"
                    f"Skipping child wallet funding and proceeding directly to volume generation..."
                )
            )
            wallets_already_funded = True
        else:
            funded_count = funding_status.get("funded_wallets", 0)
            total_count = funding_status.get("total_wallets", 0)
            if funded_count > 0:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=(
                        f"🔄 Funding {total_count - funded_count} remaining child wallets...\n\n"
                        f"({funded_count}/{total_count} wallets already funded)"
                    )
                )
            else:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=f"🔄 Funding {total_count} child wallets..."
                )
            wallets_already_funded = False
        
        # Skip funding if wallets are already sufficiently funded
        if not wallets_already_funded:
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
                    batch_id=batch_id,
                    verify_transfers=True  # Enable verification to check if transfers were successful
                )
                
                # Update session with batch ID
                session_manager.update_session_value(user.id, "batch_id", batch_id)
                
                # Mark transfers as initiated to prevent duplicates
                session_manager.update_session_value(user.id, "transfers_initiated", True)
                
                # Store the verification results for later reference
                session_manager.update_session_value(user.id, "verification_results", funding_result.get("verification_results", []))
                
                # Process verification results to trigger transaction events
                if "verification_results" in funding_result and isinstance(funding_result["verification_results"], list):
                    for verification in funding_result["verification_results"]:
                        child_wallet = verification.get("wallet_address")
                        is_verified = verification.get("verified", False)
                        initial_balance = verification.get("initial_balance", 0)
                        final_balance = verification.get("final_balance", 0)
                        difference = verification.get("difference", 0)
                        
                        # Generate a mock transaction hash for event tracking
                        tx_hash = f"tx_{batch_id}_{child_wallet[-6:]}"
                        
                        # Emit appropriate event based on verification result
                        if is_verified:
                            # Emit transaction confirmed event
                            await event_system.emit("transaction_confirmed", {
                                "tx_hash": tx_hash,
                                "from": mother_wallet,
                                "to": child_wallet,
                                "amount": amount_per_wallet,
                                "token_symbol": "SOL",
                                "difference": difference
                            })
                        else:
                            # Emit transaction failed event with error info
                            await event_system.emit("transaction_failed", {
                                "tx_hash": tx_hash,
                                "from": mother_wallet,
                                "to": child_wallet,
                                "amount": amount_per_wallet,
                                "token_symbol": "SOL",
                                "error": f"Verification failed. Balance changed from {initial_balance} to {final_balance} SOL."
                            })
                
                # Provide summary of transfer results
                successful_transfers = funding_result.get("successful_transfers", 0)
                failed_transfers = funding_result.get("failed_transfers", 0)
                total_transfers = successful_transfers + failed_transfers
                
                # Log the funding result
                logger.info(
                    f"Direct funding result for user {user.id}",
                    extra={
                        "user_id": user.id, 
                        "batch_id": batch_id, 
                        "result": funding_result,
                        "successful_transfers": successful_transfers,
                        "failed_transfers": failed_transfers
                    }
                )
                
                # Send a summary message
                await context.bot.send_message(
                    chat_id=user.id,
                    text=(
                        f"📊 Transfer Summary\n\n"
                        f"✅ Successful: {successful_transfers}/{total_transfers}\n"
                        f"❌ Failed: {failed_transfers}/{total_transfers}\n\n"
                        f"Batch ID: {batch_id}\n"
                        f"Status: {funding_result.get('status', 'unknown')}"
                    )
                )
            
            else:
                logger.info(
                    f"Started execution using API endpoint for user {user.id}",
                    extra={"user_id": user.id, "run_id": run_id, "result": result}
                )
                
                # Also transition to child balances overview for API endpoint case
                await context.bot.send_message(
                    chat_id=user.id,
                    text=(
                        "✅ Execution started via API endpoint!\n\n"
                        "Now fetching child wallet balances to show you an overview..."
                    )
                )
                
                return ConversationState.CHILD_BALANCES_OVERVIEW
        
        else:
            # Wallets are already funded, skip funding step entirely
            logger.info(f"Skipping funding step for user {user.id} - wallets already sufficiently funded")
            
            # Mark transfers as already completed to prevent duplicate execution attempts
            session_manager.update_session_value(user.id, "transfers_initiated", True)
            
            # Send confirmation message
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    "✅ Child wallets already have sufficient balance!\n\n"
                    "Proceeding directly to balance overview..."
                )
            )
        
        # Both funded and already-funded paths transition to child balances overview
        # Instead of immediately starting volume generation, transition to child balances overview
        # This allows users to see their child wallet balances and choose what to do next
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                "✅ Ready for volume generation!\n\n"
                "Now fetching current balances to show you an overview..."
            )
        )
        
        return ConversationState.CHILD_BALANCES_OVERVIEW
        
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


async def check_child_wallets_funding_status(user_id: int, required_amount_per_wallet: float, tolerance: float = 0.0) -> Dict[str, Any]:
    """
    Check if child wallets already have sufficient balance for volume generation.
    
    Args:
        user_id: Telegram user ID
        required_amount_per_wallet: Required SOL amount per child wallet
        tolerance: Tolerance for balance checking (default: 0.0 SOL - no tolerance)
        
    Returns:
        Dictionary containing funding status information
    """
    try:
        child_wallets = session_manager.get_session_value(user_id, "child_wallets")
        if not child_wallets:
            return {
                "all_funded": False,
                "error": "No child wallets found in session"
            }
        
        logger.info(f"Checking funding status for {len(child_wallets)} child wallets (required: {required_amount_per_wallet} SOL each, tolerance: {tolerance} SOL, minimum required: {required_amount_per_wallet + tolerance} SOL per wallet)")
        
        funded_wallets = []
        unfunded_wallets = []
        check_errors = []
        
        # Pre-calculate the minimum required balance including tolerance
        minimum_required_balance = required_amount_per_wallet + tolerance
        logger.info(f"Each wallet must have at least {minimum_required_balance} SOL to be considered funded (required: {required_amount_per_wallet}, tolerance: {tolerance})")
        
        for wallet_address in child_wallets:
            try:
                balance_info = api_client.check_balance(wallet_address)
                current_balance = 0
                
                # Extract SOL balance
                if isinstance(balance_info, dict) and 'balances' in balance_info:
                    for token_balance in balance_info['balances']:
                        if token_balance.get('symbol') == 'SOL' or token_balance.get('token') == "So11111111111111111111111111111111111111112":
                            current_balance = token_balance.get('amount', 0)
                            break
                
                # Check if wallet has sufficient balance (accounting for gas fees)
                # Wallet needs: required_amount + tolerance (for gas fees)
                minimum_required_balance = required_amount_per_wallet + tolerance
                
                if current_balance >= minimum_required_balance:
                    funded_wallets.append({
                        "address": wallet_address,
                        "balance": current_balance,
                        "status": "sufficient"
                    })
                    logger.debug(f"Wallet {wallet_address}: {current_balance} SOL (sufficient - needs {minimum_required_balance} SOL)")
                else:
                    unfunded_wallets.append({
                        "address": wallet_address,
                        "balance": current_balance,
                        "required": minimum_required_balance,
                        "status": "insufficient"
                    })
                    logger.debug(f"Wallet {wallet_address}: {current_balance} SOL (insufficient - needs {minimum_required_balance} SOL)")
                    
            except Exception as e:
                logger.warning(f"Error checking balance for wallet {wallet_address}: {str(e)}")
                check_errors.append({
                    "address": wallet_address,
                    "error": str(e)
                })
                unfunded_wallets.append({
                    "address": wallet_address,
                    "balance": 0,
                    "required": required_amount_per_wallet,
                    "status": "check_failed"
                })
        
        all_funded = len(unfunded_wallets) == 0 and len(check_errors) == 0
        
        result = {
            "all_funded": all_funded,
            "total_wallets": len(child_wallets),
            "funded_wallets": len(funded_wallets),
            "unfunded_wallets": len(unfunded_wallets),
            "check_errors": len(check_errors),
            "required_per_wallet": required_amount_per_wallet,
            "tolerance": tolerance,
            "funded_wallet_details": funded_wallets,
            "unfunded_wallet_details": unfunded_wallets,
            "error_details": check_errors
        }
        
        logger.info(f"Funding status check complete: {len(funded_wallets)}/{len(child_wallets)} wallets sufficiently funded")
        return result
        
    except Exception as e:
        logger.error(f"Error checking child wallets funding status: {str(e)}")
        return {
            "all_funded": False,
            "error": f"Failed to check funding status: {str(e)}"
        }


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
            
            # Also store the full child wallets data (with private keys) for return funds functionality
            session_manager.update_session_value(user.id, "child_wallets_data", child_wallets)
            
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


async def child_balances_overview_handler(update: Update, context: CallbackContext) -> int:
    """
    Handle the child balances overview state - fetch balances and show options.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.effective_user if update.message else update.callback_query.from_user
    query = update.callback_query  # Might be None if transitioned directly

    if query:
        await query.answer()
        action = query.data
        if action == "trigger_volume_generation":
            return await trigger_volume_generation(update, context)
        elif action == "trigger_return_all_funds":
            return await trigger_return_all_funds(update, context)
        elif action == "retry_fetch_child_balances":
            pass  # Fall through to fetch balances again

    # This part runs on initial entry to the state or if retry button was pressed
    loading_message = await context.bot.send_message(
        chat_id=user.id,
        text="🔍 Fetching child wallet balances, please wait..."
    )

    child_wallets_data = session_manager.get_session_value(user.id, "child_wallets_data")
    if not child_wallets_data:
        logger.error(f"Child wallets data not found in session for user {user.id}")
        await loading_message.edit_text(format_error_message("Critical error: Child wallet data missing. Please /start again."))
        return ConversationHandler.END

    child_balances_info = []
    has_errors = False
    for child_data in child_wallets_data:
        child_address = child_data.get('address')
        if not child_address:
            continue
        try:
            balance_response = api_client.check_balance(child_address)  # This returns SOL balance primarily
            sol_balance = 0
            if balance_response and 'balances' in balance_response:
                for bal_entry in balance_response['balances']:
                    if bal_entry.get('symbol') == 'SOL' or bal_entry.get('token') == "So11111111111111111111111111111111111111112":
                        sol_balance = bal_entry.get('amount', 0)
                        break
            child_balances_info.append({'address': child_address, 'balance_sol': sol_balance})
        except ApiClientError as e:
            logger.warning(f"Failed to fetch balance for child {child_address} for user {user.id}: {e}")
            child_balances_info.append({'address': child_address, 'balance_sol': 'Error'})
            has_errors = True

    overview_message_text = format_child_balances_overview(child_balances_info)

    keyboard_buttons = [
        [build_button("🚀 Start Volume Generation", "trigger_volume_generation")],
        [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")]
    ]
    if has_errors:
        keyboard_buttons.insert(0, [build_button("🔄 Retry Fetch Balances", "retry_fetch_child_balances")])

    await loading_message.edit_text(
        text=overview_message_text,
        reply_markup=InlineKeyboardMarkup(keyboard_buttons),
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationState.CHILD_BALANCES_OVERVIEW  # Stay in this state to handle button presses


async def trigger_volume_generation(update: Update, context: CallbackContext) -> int:
    """
    Trigger the volume generation process.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()

    run_id = session_manager.get_session_value(user.id, "run_id")

    if not run_id:
        logger.error(f"Missing run_id for execution for user {user.id}")
        await query.edit_message_text(format_error_message("Session data missing for execution. Please /start again."))
        return ConversationHandler.END

    await query.edit_message_text("🚀 Initiating volume generation sequence...")

    try:
        # Set up event handlers for transaction updates
        await setup_transaction_event_handlers(user.id, context)
        
        logger.info(f"User {user.id} triggered volume generation for run_id {run_id}.")
        await context.bot.send_message(
            chat_id=user.id,
            text="💫 Volume generation process has been initiated!\n\nYou'll receive updates as transfers are processed between child wallets.",
            reply_markup=InlineKeyboardMarkup([
                [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")],
                [build_button("❌ Cancel", "cancel")]
            ])
        )
        
        return ConversationState.EXECUTION

    except Exception as e:
        logger.error(f"Error starting volume generation for user {user.id}: {e}")
        await context.bot.send_message(
            chat_id=user.id,
            text=format_error_message(f"Could not start volume generation: {e}")
        )
        return ConversationState.CHILD_BALANCES_OVERVIEW  # Stay to allow retry or return funds


async def trigger_return_all_funds(update: Update, context: CallbackContext) -> int:
    """
    Return all funds from child wallets to the mother wallet.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()

    logger.info(f"User {user.id} triggered return all funds operation")

    # Send initial progress message
    progress_message = await query.edit_message_text(
        "💸 **Fund Return Process Started**\n\n"
        "🔍 Checking child wallet balances...",
        parse_mode=ParseMode.MARKDOWN
    )

    mother_wallet_address = session_manager.get_session_value(user.id, "mother_wallet")
    child_wallets_data = session_manager.get_session_value(user.id, "child_wallets_data")  # List of {'address': ..., 'private_key': ...}

    if not mother_wallet_address or not child_wallets_data:
        logger.error(f"Missing mother or child wallet data for fund return for user {user.id}")
        await query.edit_message_text(
            format_error_message("Critical data missing. Please /start again."),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END

    logger.info(f"Starting fund return for user {user.id}: {len(child_wallets_data)} child wallets -> mother wallet {mother_wallet_address}")

    return_results = []
    total_wallets = len(child_wallets_data)
    processed_count = 0

    # Update the progress message instead of creating a new one
    await progress_message.edit_text(
        format_return_funds_progress(
            processed=processed_count,
            total=total_wallets,
            successful=0,
            skipped=0,
            failed=0,
            current_wallet=None
        ),
        parse_mode=ParseMode.MARKDOWN
    )

    for child_data in child_wallets_data:
        child_address = child_data.get('address')
        child_pk = child_data.get('private_key')

        if not child_address or not child_pk:
            logger.warning(f"Skipping child wallet due to missing address or PK: {child_address} for user {user.id}")
            return_results.append({
                'child_address': child_address or 'Unknown',
                'status': 'skipped',
                'error': 'Missing address or private key in session data.'
            })
            continue

        try:
            logger.info(f"Processing fund return from child wallet {child_address} for user {user.id}")
            
            # Check current balance first
            balance_response = api_client.check_balance(child_address)
            current_balance = 0
            if balance_response and 'balances' in balance_response:
                for bal_entry in balance_response['balances']:
                    if bal_entry.get('symbol') == 'SOL' or bal_entry.get('token') == "So11111111111111111111111111111111111111112":
                        current_balance = bal_entry.get('amount', 0)
                        break
            
            logger.info(f"Child wallet {child_address} has balance: {current_balance} SOL")
            
            # Skip if balance is too low (less than typical gas fee)
            if current_balance < 0.001:
                logger.info(f"Skipping child wallet {child_address} due to low balance: {current_balance} SOL")
                return_results.append({
                    'child_address': child_address,
                    'status': 'skipped',
                    'error': f'Balance too low ({current_balance:.6f} SOL) to cover gas fees.'
                })
                continue

            # Use the transfer_child_to_mother method from api_client
            # Return ALL funds - let the API handle gas fee calculation automatically
            logger.info(f"Attempting to return ALL funds from {child_address} to mother wallet {mother_wallet_address}")

            # Call the API to return ALL funds (API will automatically handle gas fees)
            transfer_result = await api_client.transfer_child_to_mother(
                child_wallet=child_address,
                child_private_key=child_pk,
                mother_wallet=mother_wallet_address,
                amount=None,  # Use None to trigger returnAllFunds=true
                token_address="So11111111111111111111111111111111111111112",  # SOL
                verify_transfer=False  # Skip verification for speed
            )

            logger.info(f"Transfer result for {child_address}: {transfer_result}")

            if transfer_result and transfer_result.get("status") == "success":
                # Get the actual amount returned from the API response
                actual_amount_returned = transfer_result.get('amount', 0)
                if transfer_result.get('api_response'):
                    actual_amount_returned = transfer_result['api_response'].get('amountReturnedSol', actual_amount_returned)
                
                logger.info(f"Successfully returned {actual_amount_returned} SOL from {child_address} to mother wallet")
                return_results.append({
                    'child_address': child_address,
                    'status': 'success',
                    'amount_returned_sol': actual_amount_returned,
                    'tx_id': transfer_result.get('tx_id', transfer_result.get('transactionId', 'N/A'))
                })
            else:
                error_msg = transfer_result.get('error', transfer_result.get('message', 'Unknown API error'))
                logger.warning(f"Failed to transfer from {child_address}: {error_msg}")
                return_results.append({
                    'child_address': child_address,
                    'status': 'failed',
                    'error': error_msg
                })

        except ApiClientError as e:
            logger.error(f"API Error returning funds from {child_address} for user {user.id}: {e}")
            return_results.append({
                'child_address': child_address,
                'status': 'failed',
                'error': str(e)
            })
        except Exception as e_outer:
            logger.error(f"Unexpected error returning funds from {child_address} for user {user.id}: {e_outer}")
            return_results.append({
                'child_address': child_address,
                'status': 'failed',
                'error': f"Unexpected: {str(e_outer)}"
            })
        
        processed_count += 1
        # Update progress every few wallets
        if processed_count % 3 == 0 or processed_count == total_wallets:
            try:
                success_count = len([r for r in return_results if r.get('status') == 'success'])
                skip_count = len([r for r in return_results if r.get('status') == 'skipped'])
                fail_count = len([r for r in return_results if r.get('status') == 'failed'])
                
                await progress_message.edit_text(
                    format_return_funds_progress(
                        processed=processed_count,
                        total=total_wallets,
                        successful=success_count,
                        skipped=skip_count,
                        failed=fail_count,
                        current_wallet=child_address if processed_count < total_wallets else None
                    ),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass  # Continue if progress update fails

        await asyncio.sleep(0.5)  # Small delay between API calls

    summary_message = format_return_funds_summary(return_results, mother_wallet_address)
    await context.bot.send_message(chat_id=user.id, text=summary_message, parse_mode=ParseMode.MARKDOWN)

    # Clean up session and end
    session_manager.clear_session(user.id)
    await context.bot.send_message(user.id, "Operations complete. Type /start to begin a new session.")
    return ConversationHandler.END


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
                CallbackQueryHandler(start_execution, pattern=r"^start_execution$"),
                CallbackQueryHandler(trigger_return_all_funds, pattern=r"^trigger_return_all_funds$"),
                CallbackQueryHandler(regenerate_preview, pattern=r"^regenerate$")
            ],
            ConversationState.AWAIT_FUNDING: [
                CallbackQueryHandler(check_balance, pattern=r"^check_balance$"),
                CallbackQueryHandler(start_execution, pattern=r"^start_execution$"),
                CallbackQueryHandler(trigger_return_all_funds, pattern=r"^trigger_return_all_funds$")
            ],
            ConversationState.CHILD_BALANCES_OVERVIEW: [
                CallbackQueryHandler(trigger_volume_generation, pattern=r"^trigger_volume_generation$"),
                CallbackQueryHandler(trigger_return_all_funds, pattern=r"^trigger_return_all_funds$"),
                CallbackQueryHandler(regenerate_preview, pattern=r"^regenerate_preview$")
            ],
            ConversationState.EXECUTION: [
                CallbackQueryHandler(cancel, pattern=r"^cancel$"),
                CallbackQueryHandler(trigger_return_all_funds, pattern=r"^trigger_return_all_funds$")
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