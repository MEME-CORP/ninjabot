from typing import Dict, List, Any, Optional
import asyncio
import time
import random
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

from bot.config import ConversationState, CallbackPrefix, MIN_CHILD_WALLETS, SERVICE_FEE_RATE, CONVERSATION_TIMEOUT
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
    format_existing_child_wallets_found_message,
    format_no_child_wallets_found_message,
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
    format_return_funds_progress,
    format_volume_generation_insufficient_balance_message,
    format_sell_remaining_balance_summary
)
from bot.api.api_client import api_client, ApiClientError
from bot.events.event_system import event_system, TransactionConfirmedEvent, TransactionFailedEvent
from bot.utils.balance_poller import balance_poller
from bot.state.session_manager import session_manager


# Helper function for the background job
async def volume_generation_job(context: CallbackContext):
    """The background job that executes the volume run and reports back."""
    job_data = context.job.data
    user_id = job_data['user_id']

    logger.info(f"🔥 VOLUME_GENERATION_JOB STARTED - User: {user_id}, Run ID: {job_data.get('run_id')}")
    print(f"🔥 VOLUME_GENERATION_JOB STARTED - User: {user_id}, Run ID: {job_data.get('run_id')}")

    try:
        # Execute the volume run with enhanced logging and error handling
        logger.info(
            f"Starting volume generation execution for user {user_id}",
            extra={
                "user_id": user_id,
                "run_id": job_data.get('run_id'),
                "total_trades": len(job_data.get('trades', [])),
                "child_wallets_count": len(job_data.get('child_wallets', [])),
                "token_address": job_data.get('token_address')
            }
        )
        
        run_results = await api_client.execute_spl_volume_run(
            child_wallets=job_data['child_wallets'],
            child_private_keys=job_data['child_private_keys'],
            trades=job_data['trades'],
            token_address=job_data['token_address'],
            verify_transfers=True
        )
        # Enhanced logging for debugging
        logger.info(
            f"Volume run finished for user {user_id}",
            extra={
                "user_id": user_id,
                "run_id": job_data.get('run_id'),
                "status": run_results.get('status'),
                "trades_succeeded": run_results.get('trades_succeeded', 0),
                "trades_failed": run_results.get('trades_failed', 0),
                "total_trades": run_results.get('total_trades', 0),
                "duration": run_results.get('duration', 0)
            }
        )

        # Format a comprehensive SPL volume generation summary message
        status_emoji = {
            "success": "✅",
            "partial_success": "⚠️", 
            "failed": "❌",
            "in_progress": "🔄"
        }.get(run_results.get("status", "failed"), "ℹ️")

        token_address = job_data.get('token_address', 'Unknown')
        summary_message = (
            f"{status_emoji} **SPL Volume Generation Complete**\n\n"
            f"**Token:** `{token_address[:8]}...{token_address[-8:] if len(token_address) > 16 else token_address}`\n"
            f"**Status:** {run_results.get('status', 'N/A').replace('_', ' ').title()}\n"
            f"**Duration:** {run_results.get('duration', 0):.2f} seconds\n"
            f"**Batch ID:** `{run_results.get('batch_id', 'N/A')}`\n\n"
            f"📊 **SPL Trading Volume Summary:**\n"
            f"  - Total SOL Volume: {run_results.get('total_volume_sol', 0):.6f} SOL\n"
            f"  - Buy Operations: {run_results.get('buys_succeeded', 0)} successful\n"
            f"  - Sell Operations: {run_results.get('sells_succeeded', 0)} successful\n"
            f"  - Failed Swaps: {run_results.get('swaps_failed', 0)}\n"
            f"  - Total Swaps Executed: {run_results.get('swaps_executed', 0)}\n"
        )
        
        # Add additional details for partial success or failures
        if run_results.get('status') in ['partial_success', 'failed']:
            total_operations = run_results.get('buys_succeeded', 0) + run_results.get('sells_succeeded', 0) + run_results.get('swaps_failed', 0)
            if total_operations > 0:
                failure_rate = (run_results.get('swaps_failed', 0) / total_operations) * 100
                summary_message += f"  - Failure Rate: {failure_rate:.1f}%\n"

        await context.bot.send_message(
            chat_id=user_id,
            text=summary_message,
            parse_mode=ParseMode.MARKDOWN
        )

        # Offer next steps
        await context.bot.send_message(
            chat_id=user_id,
            text="What would you like to do next?",
            reply_markup=InlineKeyboardMarkup([
                [build_button("🪙 Sell Remaining Token Balance", "sell_remaining_balance")],
                [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")],
                [build_button("🔄 Finish and Start New Run", "finish_and_restart")]
            ])
        )

    except Exception as e:
        # Enhanced error logging with context
        logger.error(
            f"Critical error in volume generation job for user {user_id}",
            extra={
                "user_id": user_id,
                "run_id": job_data.get('run_id'),
                "error_type": type(e).__name__,
                "error_message": str(e),
                "job_data_keys": list(job_data.keys()) if job_data else [],
                "trades_count": len(job_data.get('trades', [])) if job_data else 0
            },
            exc_info=True
        )
        
        # Send user-friendly SPL volume generation error message
        token_address = job_data.get('token_address', 'Unknown')
        error_details = (
            f"❌ **SPL Volume Generation Failed**\n\n"
            f"**Token:** `{token_address[:8]}...{token_address[-8:] if len(token_address) > 16 else token_address}`\n"
            f"**Error:** {type(e).__name__}\n"
            f"**Details:** {str(e)}\n"
            f"**Run ID:** `{job_data.get('run_id', 'N/A')}`\n\n"
            f"Please try starting a new SPL volume generation run. "
            f"If the issue persists, check your wallet balances, token availability, and network connectivity."
        )
        
        await context.bot.send_message(
            chat_id=user_id,
            text=error_details,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Offer retry option
        await context.bot.send_message(
            chat_id=user_id,
            text="What would you like to do next?",
            reply_markup=InlineKeyboardMarkup([
                [build_button("🪙 Sell Remaining Token Balance", "sell_remaining_balance")],
                [build_button("🔄 Start New Run", "finish_and_restart")],
                [build_button("💸 Return All Funds", "trigger_return_all_funds")]
            ])
        )


# Handler functions
async def start(update: Update, context: CallbackContext) -> int:
    """
    Start the conversation and show activity selection.

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

    # Import message formatters
    from bot.utils.message_utils import format_activity_selection_message

    # Build keyboard with activity options
    keyboard = [
        [build_button("📊 Volume Generation", f"{CallbackPrefix.ACTIVITY}{CallbackPrefix.VOLUME_GENERATION}")],
        [build_button("🚀 Token Bundling (PumpFun)", f"{CallbackPrefix.ACTIVITY}{CallbackPrefix.BUNDLING}")]
    ]

    # Send activity selection message
    message = update.effective_message
    await message.reply_text(
        format_activity_selection_message(),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

    return ConversationState.ACTIVITY_SELECTION


async def activity_choice(update: Update, context: CallbackContext) -> int:
    """
    Handle activity selection (Volume Generation vs Bundling).

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
    
    # Import message formatters
    from bot.utils.message_utils import format_activity_confirmation_message

    if choice == f"{CallbackPrefix.ACTIVITY}{CallbackPrefix.VOLUME_GENERATION}":
        # User selected Volume Generation
        session_manager.update_session_value(user.id, "activity_type", "volume_generation")
        
        logger.info(
            f"User {user.id} selected Volume Generation",
            extra={"user_id": user.id, "activity": "volume_generation"}
        )
        
        # Show confirmation and redirect to wallet setup for volume generation
        await query.edit_message_text(
            format_activity_confirmation_message("volume_generation"),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Add small delay for user to read confirmation
        await asyncio.sleep(2)
        
        # Redirect to wallet choice for volume generation workflow
        return await start_volume_generation_workflow(update, context)
    
    elif choice == f"{CallbackPrefix.ACTIVITY}{CallbackPrefix.BUNDLING}":
        # User selected Bundling
        session_manager.update_session_value(user.id, "activity_type", "bundling")
        
        logger.info(
            f"User {user.id} selected Token Bundling",
            extra={"user_id": user.id, "activity": "bundling"}
        )
        
        # Show confirmation and redirect to bundling workflow
        await query.edit_message_text(
            format_activity_confirmation_message("bundling"),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Add small delay for user to read confirmation
        await asyncio.sleep(2)
        
        # Redirect to bundling wallet setup
        return await start_bundling_workflow(update, context)
    
    else:
        # Invalid choice, return to activity selection
        logger.warning(f"Invalid activity choice: {choice} from user {user.id}")
        return await start(update, context)


async def start_volume_generation_workflow(update: Update, context: CallbackContext) -> int:
    """
    Start the volume generation workflow with wallet setup.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
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

    # Add back button to return to activity selection
    keyboard.append([build_button("« Back to Activities", "back_to_activities")])

    # Send welcome message with keyboard
    await query.edit_message_text(
        format_welcome_message(),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

    return ConversationState.WALLET_CHOICE


async def start_bundling_workflow(update: Update, context: CallbackContext) -> int:
    """
    Start the bundling workflow with airdrop wallet setup.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
    # Initialize PumpFun client
    try:
        from bot.api.pumpfun_client import PumpFunClient
        pumpfun_client = PumpFunClient()
        
        # Store client in session for later use
        session_manager.update_session_value(user.id, "pumpfun_client", pumpfun_client)
        
        # Check PumpFun API health
        health_status = pumpfun_client.health_check()
        if not health_status.get("api_reachable", False):
            logger.error(
                f"PumpFun API not reachable for user {user.id}",
                extra={"user_id": user.id, "health_status": health_status}
            )
            
            # Show error and return to activity selection
            keyboard = [[build_button("« Back to Activities", "back_to_activities")]]
            await query.edit_message_text(
                "❌ **PumpFun API Unavailable**\n\n"
                "The PumpFun API is currently not reachable. Please try again later or contact support.\n\n"
                f"Error: {health_status.get('error', 'Unknown error')}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
            return ConversationState.ACTIVITY_SELECTION
        
    except Exception as e:
        logger.error(
            f"Failed to initialize PumpFun client for user {user.id}: {str(e)}",
            extra={"user_id": user.id}
        )
        
        # Show error and return to activity selection
        keyboard = [[build_button("« Back to Activities", "back_to_activities")]]
        await query.edit_message_text(
            "❌ **PumpFun Setup Error**\n\n"
            "Failed to initialize PumpFun integration. Please try again later.\n\n"
            f"Error: {str(e)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.ACTIVITY_SELECTION
    
    # Build keyboard for airdrop wallet setup
    keyboard = [
        [build_button("Create Airdrop Wallet", "create_airdrop_wallet")],
        [build_button("Import Airdrop Wallet", "import_airdrop_wallet")],
        [build_button("« Back to Activities", "back_to_activities")]
    ]

    await query.edit_message_text(
        "🏪 **Airdrop Wallet Setup**\n\n"
        "First, let's set up your airdrop (mother) wallet that will fund your bundled wallets.\n\n"
        "Choose how you want to set up your airdrop wallet:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

    return ConversationState.BUNDLING_WALLET_SETUP


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
    
    elif choice == "back_to_activities":
        # Go back to activity selection
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

                # Build keyboard with options - conditional logic to prevent data fragmentation
                keyboard = []

                if child_wallets:
                    # Only show relevant options when child wallets exist - prevents data fragmentation
                    logger.info(
                        f"Found {len(child_wallets)} existing child wallets for mother wallet",
                        extra={"user_id": user.id, "mother_wallet": wallet_address, "child_count": len(child_wallets)}
                    )
                    
                    keyboard.append([build_button("Use Existing Child Wallets", f"use_existing_children_{wallet_index}")])
                    # Optional warning-level replace option
                    keyboard.append([build_button("⚠️ Replace Child Wallets", f"create_new_children_{wallet_index}")])
                    
                    # Store child wallets in session for existing wallets
                    child_addresses = [wallet.get('address') for wallet in child_wallets if wallet.get('address')]
                    session_manager.update_session_value(user.id, "child_wallets", child_addresses)
                    session_manager.update_session_value(user.id, "child_wallets_data", child_wallets)
                    session_manager.update_session_value(user.id, "num_child_wallets", len(child_addresses))
                    
                    # Send message with existing child wallets context
                    await query.edit_message_text(
                        format_existing_child_wallets_found_message(wallet_address, len(child_wallets)),
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    return ConversationState.CHILD_WALLET_CHOICE
                else:
                    # No existing child wallets, go directly to creation - streamlined UX
                    logger.info(
                        f"No existing child wallets found for mother wallet, proceeding to creation",
                        extra={"user_id": user.id, "mother_wallet": wallet_address}
                    )
                    
                    await query.edit_message_text(
                        format_no_child_wallets_found_message(wallet_address),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    # Initialize empty session data for new child wallet creation
                    session_manager.update_session_value(user.id, "child_wallets", [])
                    session_manager.update_session_value(user.id, "child_wallets_data", [])
                    session_manager.update_session_value(user.id, "num_child_wallets", 0)
                    
                    return ConversationState.NUM_CHILD_WALLETS

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
    Handle the volume amount input for SPL token volume generation.

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
        f"User {user.id} set SPL volume generation amount to {volume} SOL",
        extra={"user_id": user.id, "volume": volume, "operation": "spl_volume_generation"}
    )

    # Ask for SPL token contract address with enhanced guidance
    volume_msg = format_volume_confirmation_message(volume)
    spl_guidance = (
        f"\n\n📝 **SPL Token Contract Address**\n"
        f"Now enter the contract address of the SPL token you want to generate volume for.\n\n"
        f"This should be a 44-character Solana mint address.\n"
        f"Example: `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` (USDC)"
    )
    
    await update.message.reply_text(volume_msg + spl_guidance, parse_mode=ParseMode.MARKDOWN)

    return ConversationState.TOKEN_ADDRESS


async def token_address(update: Update, context: CallbackContext) -> int:
    """
    Handle the SPL token contract address input for volume generation.

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
    log_validation_result(user.id, "spl_token_address", is_valid, value_or_error)

    if not is_valid:
        # Invalid input, send error and ask again with SPL-specific guidance
        error_msg = format_error_message(
            f"Invalid SPL token contract address: {value_or_error}\n\n"
            "Please provide a valid Solana token mint address (44 characters, base58 encoded).\n"
            "Example: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        )
        await update.message.reply_text(error_msg)
        return ConversationState.TOKEN_ADDRESS

    # Valid input, store and continue
    token_addr = value_or_error
    session_manager.update_session_value(user.id, "token_address", token_addr)

    logger.info(
        f"User {user.id} set SPL token contract address to {token_addr}",
        extra={"user_id": user.id, "spl_token_address": token_addr, "operation": "volume_generation"}
    )

    # Prepare and show schedule preview
    await generate_preview(update.effective_message, context)

    return ConversationState.PREVIEW_SCHEDULE


async def generate_preview(message: telegram.Message, context: CallbackContext) -> None:
    """
    Generate and show the schedule preview.

    Args:
        message: The Telegram message object to reply to or edit.
        context: The context object
    """
    user = message.from_user

    # Get session data
    mother_wallet = session_manager.get_session_value(user.id, "mother_wallet")
    child_wallets = session_manager.get_session_value(user.id, "child_wallets")
    token_address = session_manager.get_session_value(user.id, "token_address")
    total_volume = session_manager.get_session_value(user.id, "total_volume")
    num_child_wallets = session_manager.get_session_value(user.id, "num_child_wallets")

    # Show loading message
    loading_message = await context.bot.send_message(
        chat_id=user.id,
        text="Generating transfer schedule..."
    )

    try:
        # Generate natural trading schedule with separated phases for better stealth
        schedule = api_client.generate_natural_trading_schedule(
            mother_wallet=mother_wallet,
            child_wallets=child_wallets,
            token_address=token_address,
            total_volume=total_volume,
            pattern_type="separated_phases"
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

        # Format and show SPL volume generation preview
        preview_text = format_schedule_preview(
            schedule=schedule.get("transfers", []),
            total_volume=total_volume,
            token_address=token_address,
            num_child_wallets=num_child_wallets,
            mother_wallet_address=mother_wallet
        )
        
        # Add SPL-specific context to preview
        spl_context = (
            f"\n\n🔄 **SPL Volume Generation Setup**\n"
            f"This will generate {total_volume} SOL worth of trading volume "
            f"for the SPL token: `{token_address[:8]}...{token_address[-8:]}`\n\n"
            f"The volume will be distributed across {num_child_wallets} child wallets "
            f"through randomized transfers to simulate legitimate trading activity."
        )
        preview_text += spl_context

        await loading_message.edit_text(
            preview_text,
            parse_mode=ParseMode.MARKDOWN
        )

        # Check if child wallets are ready for SPL swaps
        loading_spl_check = await context.bot.send_message(
            chat_id=user.id,
            text="🔍 Checking if child wallets are ready for SPL swaps..."
        )
        
        try:
            # Calculate minimum swap amount based on total volume
            min_swap_amount = total_volume / (len(child_wallets) * 10) if child_wallets else 0.0001
            
            # Check SPL swap readiness
            readiness_check = api_client.check_spl_swap_readiness(
                child_wallets=child_wallets,
                min_swap_amount_sol=min_swap_amount
            )
            
            # Store readiness check in session for later use
            session_manager.update_session_value(user.id, "spl_readiness_check", readiness_check)
            session_manager.update_session_value(user.id, "child_wallets_need_funding", readiness_check['status'] != 'ready')
            
            if readiness_check['status'] == 'ready':
                # All wallets ready - show positive message and continue
                await loading_spl_check.edit_text(
                    f"✅ **All Child Wallets Ready**\n\n"
                    f"All {readiness_check['total_wallets']} child wallets have sufficient balance for SPL swaps.\n"
                    f"Ready to generate {total_volume} SOL worth of volume!",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Show action button to start volume generation
                await context.bot.send_message(
                    chat_id=user.id,
                    text="🚀 Ready to start SPL volume generation!",
                    reply_markup=InlineKeyboardMarkup([
                        [build_button("🚀 Start SPL Volume Generation", "start_execution")],
                        [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")]
                    ])
                )
            else:
                # Some wallets need funding - show detailed message with solutions
                insufficient_message = format_volume_generation_insufficient_balance_message(
                    total_wallets=readiness_check['total_wallets'],
                    wallets_with_insufficient_balance=readiness_check['wallets_insufficient'],
                    required_per_wallet=readiness_check['min_required_per_wallet'],
                    reserved_per_wallet=readiness_check['reserved_amount_per_wallet'],
                    min_swap_amount=min_swap_amount
                )
                
                await loading_spl_check.edit_text(insufficient_message, parse_mode=ParseMode.MARKDOWN)
                
                # Show appropriate action buttons based on readiness status
                if readiness_check['status'] == 'partially_ready':
                    keyboard = [
                        [build_button("💰 Fund Remaining Wallets", "fund_child_wallets")],
                        [build_button("🚀 Start with Ready Wallets", "start_execution")],
                        [build_button("🔄 Check Again", "check_spl_readiness")]
                    ]
                else:
                    keyboard = [
                        [build_button("💰 Fund Child Wallets", "fund_child_wallets")],
                        [build_button("🔄 Check Again", "check_spl_readiness")],
                        [build_button("💸 Return All Funds", "trigger_return_all_funds")]
                    ]
                
                await context.bot.send_message(
                    chat_id=user.id,
                    text="What would you like to do?",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                return ConversationState.PREVIEW_SCHEDULE
                
        except Exception as e:
            logger.error(f"Error checking SPL readiness: {str(e)}", extra={"user_id": user.id})
            await loading_spl_check.edit_text(
                format_error_message(f"Failed to check wallet readiness: {str(e)}")
            )



    except ApiClientError as e:
        logger.error(f"Error generating schedule: {str(e)}", extra={"user_id": user.id})
        await loading_message.edit_text(
            format_error_message(f"Could not generate schedule: {str(e)}"),
            reply_markup=InlineKeyboardMarkup([[build_button("Try Again", "regenerate_preview")]])
        )


async def start_balance_polling(user_id: int, context: CallbackContext) -> None:
    """Start polling for wallet balance."""
    mother_wallet = session_manager.get_session_value(user_id, "mother_wallet")
    token_address = session_manager.get_session_value(user_id, "token_address")
    total_volume = session_manager.get_session_value(user_id, "total_volume")

    if not all([mother_wallet, token_address, total_volume]):
        logger.error("Missing session data for balance polling", extra={"user_id": user_id})
        return

    async def on_target_reached():
        balance_info = api_client.check_balance(mother_wallet, token_address)
        current_balance = next((b.get('amount', 0) for b in balance_info.get('balances', []) if b.get('symbol') == "SOL"), 0)
        await context.bot.send_message(
            chat_id=user_id,
            text=format_sufficient_balance_message(balance=current_balance, token_symbol="SOL"),
            reply_markup=InlineKeyboardMarkup([
                [build_button("Begin Transfers", "start_execution")],
                [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )

    await balance_poller.start_polling(
        wallet_address=mother_wallet,
        token_address=token_address,
        target_balance=total_volume,
        on_target_reached=on_target_reached
    )
    logger.info("Started balance polling", extra={"user_id": user_id, "wallet": mother_wallet, "target": total_volume})


async def check_balance(update: Update, context: CallbackContext) -> int:
    """Check the balance of the mother wallet."""
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()

    mother_wallet = session_manager.get_session_value(user.id, "mother_wallet")
    token_address = session_manager.get_session_value(user.id, "token_address")
    total_volume = session_manager.get_session_value(user.id, "total_volume")

    if not all([mother_wallet, token_address, total_volume]):
        await query.edit_message_text(format_error_message("Session data missing. Please restart with /start."))
        return ConversationState.START

    try:
        await query.edit_message_text(f"Checking balance for wallet: `{mother_wallet}`...", parse_mode=ParseMode.MARKDOWN)
        balance_info = api_client.check_balance(mother_wallet, token_address)
        current_balance = next((b.get('amount', 0) for b in balance_info.get('balances', []) if b.get('symbol') == "SOL"), 0)
        
        logger.info(
            f"Checked balance for user {user.id}",
            extra={"user_id": user.id, "wallet": mother_wallet, "balance": current_balance, "target": total_volume}
        )

        if current_balance >= total_volume:
            await query.edit_message_text(
                format_sufficient_balance_message(balance=current_balance, token_symbol="SOL"),
                reply_markup=InlineKeyboardMarkup([
                    [build_button("Begin Transfers", "start_execution")],
                    [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")]
                ]),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.edit_message_text(
                format_insufficient_balance_message(current_balance, total_volume, "SOL"),
                reply_markup=InlineKeyboardMarkup([
                    [build_button("Check Again", "check_balance")],
                    [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")]
                ]),
                parse_mode=ParseMode.MARKDOWN
            )
        return ConversationState.AWAIT_FUNDING

    except ApiClientError as e:
        logger.error(f"Error checking balance: {str(e)}", extra={"user_id": user.id})
        await query.edit_message_text(
            format_error_message(f"Could not check balance: {str(e)}"),
            reply_markup=InlineKeyboardMarkup([[build_button("Try Again", "check_balance")]])
        )
        return ConversationState.AWAIT_FUNDING


async def start_execution(update: Update, context: CallbackContext) -> int:
    """Start executing the transfer schedule."""
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()

    await query.edit_message_text("Starting transfer execution...", reply_markup=None)

    try:
        mother_wallet = session_manager.get_session_value(user.id, "mother_wallet")
        mother_private_key = session_manager.get_session_value(user.id, "mother_private_key")
        child_wallets = session_manager.get_session_value(user.id, "child_wallets")
        token_address = session_manager.get_session_value(user.id, "token_address", "So11111111111111111111111111111111111111112")
        total_volume = session_manager.get_session_value(user.id, "total_volume", 0)
        child_wallets_need_funding = session_manager.get_session_value(user.id, "child_wallets_need_funding", True)
        
        if not child_wallets_need_funding:
            logger.info(f"Child wallets already funded for user {user.id}, skipping funding step.")
        else:
            await context.bot.send_message(chat_id=user.id, text="🔄 Funding child wallets...")
            
            num_child_wallets = len(child_wallets)
            amount_per_wallet = total_volume / num_child_wallets if num_child_wallets > 0 else 0
            
            if not all([mother_private_key, amount_per_wallet > 0]):
                 raise ApiClientError("Missing private key or valid amount for funding.")

            funding_result = api_client.fund_child_wallets(
                mother_wallet=mother_wallet,
                child_wallets=child_wallets,
                token_address=token_address,
                amount_per_wallet=amount_per_wallet,
                mother_private_key=mother_private_key,
                verify_transfers=True
            )
            logger.info("Direct funding result", extra={"user_id": user.id, "result": funding_result})
            
            successful_transfers = funding_result.get("successful_transfers", 0)
            failed_transfers = funding_result.get("failed_transfers", 0)
            
            await context.bot.send_message(
                chat_id=user.id,
                text=f"📊 Funding Complete\n✅ Successful: {successful_transfers}\n❌ Failed: {failed_transfers}"
            )

        # Skip the balance overview and go directly to volume generation
        logger.info(f"Starting direct volume generation for user {user.id}")
        
        # Call child_balances_overview_handler to show balances first  
        loading_message = await context.bot.send_message(chat_id=user.id, text="🔍 Fetching child wallet balances...")
        
        # Get child wallets data for balance display
        child_wallets_data = session_manager.get_session_value(user.id, "child_wallets_data")
        if not child_wallets_data:
            await loading_message.edit_text(format_error_message("Child wallet data missing. Please /start again."))
            return ConversationHandler.END

        balances_info = []
        has_errors = False
        for child in child_wallets_data:
            addr = child.get('address')
            if not addr: continue
            try:
                balance_info = api_client.check_balance(addr)
                sol_balance = next((b.get('amount', 0) for b in balance_info.get('balances', []) if b.get('symbol') == 'SOL'), 0)
                balances_info.append({'address': addr, 'balance_sol': sol_balance})
            except ApiClientError as e:
                balances_info.append({'address': addr, 'balance_sol': 'Error'})
                has_errors = True
        
        overview_text = format_child_balances_overview(balances_info)
        await loading_message.edit_text(overview_text, parse_mode=ParseMode.MARKDOWN)
        
        # Now automatically start volume generation inline (no fake objects needed)
        await context.bot.send_message(
            chat_id=user.id,
            text="🚀 **Auto-starting volume generation...**",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Start volume generation directly without fake callback objects
        return await trigger_volume_generation_inline(user.id, context)

    except ApiClientError as e:
        logger.error(f"Error starting execution: {str(e)}", extra={"user_id": user.id})
        await context.bot.send_message(
            chat_id=user.id,
            text=format_error_message(f"Could not start execution: {str(e)}"),
            reply_markup=InlineKeyboardMarkup([[build_button("Try Again", "start_execution")]])
        )
        return ConversationState.AWAIT_FUNDING


async def setup_transaction_event_handlers(user_id: int, context: CallbackContext) -> None:
    """Set up event handlers for transaction events."""
    async def handle_tx_event(event):
        await context.bot.send_message(
            chat_id=user_id,
            text=format_transaction_status_message(
                tx_hash=event.data["tx_hash"],
                status=event.data["status"].capitalize(),
                from_address=event.data["from"],
                to_address=event.data["to"],
                amount=event.data["amount"],
                token_symbol=event.data.get("token_symbol", "tokens")
            )
        )

    await event_system.start()
    await event_system.subscribe("transaction_confirmed", handle_tx_event)
    await event_system.subscribe("transaction_failed", handle_tx_event)


async def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel the conversation and clean up."""
    user = update.effective_user
    logger.info(f"User {user.id} canceled the conversation")
    await balance_poller.stop_all()
    session_manager.clear_session(user.id)
    message = update.effective_message
    await message.reply_text("Operation cancelled. Type /start to begin again.")
    return ConversationHandler.END


async def timeout_handler(update: Update, context: CallbackContext) -> int:
    """Handle conversation timeout."""
    user_id = context.user_data.get('user_id')
    if user_id:
        logger.info(f"Conversation with user {user_id} timed out")
        await balance_poller.stop_all()
        session_manager.clear_session(user_id)
        await context.bot.send_message(chat_id=user_id, text="Conversation timed out. Type /start to begin again.")
    return ConversationHandler.END


async def check_child_wallets_funding_status(user_id: int, required_amount_per_wallet: float, tolerance: float = 0.0) -> Dict[str, Any]:
    """Check if child wallets already have sufficient balance."""
    try:
        child_wallets = session_manager.get_session_value(user_id, "child_wallets")
        if not child_wallets:
            return {"all_funded": False, "error": "No child wallets found"}

        funded_wallets, unfunded_wallets, check_errors = [], [], []
        minimum_required = required_amount_per_wallet + tolerance

        for addr in child_wallets:
            try:
                balance_info = api_client.check_balance(addr)
                sol_balance = next((b.get('amount', 0) for b in balance_info.get('balances', []) if b.get('symbol') == 'SOL'), 0)
                (funded_wallets if sol_balance >= minimum_required else unfunded_wallets).append(addr)
            except Exception as e:
                check_errors.append(addr)
                unfunded_wallets.append(addr)

        all_funded = not unfunded_wallets and not check_errors
        return {"all_funded": all_funded, "total_wallets": len(child_wallets), "funded_wallets": len(funded_wallets)}

    except Exception as e:
        logger.error(f"Error checking child wallets funding status: {str(e)}")
        return {"all_funded": False, "error": str(e)}


async def regenerate_preview(update: Update, context: CallbackContext) -> int:
    """Regenerate schedule preview."""
    query = update.callback_query
    await query.answer()
    await generate_preview(query.message, context)
    return ConversationState.PREVIEW_SCHEDULE


async def child_wallet_choice(update: Update, context: CallbackContext) -> int:
    """Handle choice of using existing or creating new child wallets."""
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    choice = query.data

    if "use_existing_children" in choice:
        child_wallets = session_manager.get_session_value(user.id, "child_wallets")
        await query.edit_message_text(format_child_wallets_message(len(child_wallets), child_wallets))
        return ConversationState.VOLUME_AMOUNT
    elif "create_new_children" in choice:
        await query.edit_message_text(f"How many child wallets? (min: {MIN_CHILD_WALLETS})")
        return ConversationState.NUM_CHILD_WALLETS
    
    return ConversationState.CHILD_WALLET_CHOICE


async def child_balances_overview_handler(update: Update, context: CallbackContext) -> int:
    """Fetch and display child wallet balances, then present action buttons."""
    user = update.effective_user
    loading_message = await context.bot.send_message(chat_id=user.id, text="🔍 Fetching child wallet balances...")

    child_wallets_data = session_manager.get_session_value(user.id, "child_wallets_data")
    if not child_wallets_data:
        await loading_message.edit_text(format_error_message("Child wallet data missing. Please /start again."))
        return ConversationHandler.END

    balances_info = []
    has_errors = False
    for child in child_wallets_data:
        addr = child.get('address')
        if not addr: continue
        try:
            balance_info = api_client.check_balance(addr)
            sol_balance = next((b.get('amount', 0) for b in balance_info.get('balances', []) if b.get('symbol') == 'SOL'), 0)
            balances_info.append({'address': addr, 'balance_sol': sol_balance})
        except ApiClientError as e:
            balances_info.append({'address': addr, 'balance_sol': 'Error'})
            has_errors = True
    
    overview_text = format_child_balances_overview(balances_info)
    keyboard = [[build_button("🚀 Start Volume Generation", "trigger_volume_generation")],
                [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")]]
    if has_errors:
        keyboard.insert(0, [build_button("🔄 Retry Fetch", "retry_fetch_child_balances")])

    await loading_message.edit_text(overview_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return ConversationState.CHILD_BALANCES_OVERVIEW


async def trigger_volume_generation_inline(user_id: int, context: CallbackContext) -> int:
    """Inline version of volume generation trigger that doesn't require callback query objects."""
    logger.info(f"🚀 TRIGGER_VOLUME_GENERATION_INLINE called for user {user_id}")
    print(f"🚀 TRIGGER_VOLUME_GENERATION_INLINE called for user {user_id}")

    # Enhanced session data retrieval with logging
    session_data = {
        "mother_wallet": session_manager.get_session_value(user_id, "mother_wallet"),
        "child_wallets_data": session_manager.get_session_value(user_id, "child_wallets_data"),
        "schedule": session_manager.get_session_value(user_id, "schedule"),
        "token_address": session_manager.get_session_value(user_id, "token_address"),
        "run_id": session_manager.get_session_value(user_id, "run_id")
    }

    # Comprehensive validation with detailed error reporting
    missing_data = [key for key, value in session_data.items() if not value]
    if missing_data:
        logger.error(
            f"Missing critical session data for volume generation",
            extra={
                "user_id": user_id,
                "missing_data": missing_data,
                "available_data": [key for key, value in session_data.items() if value]
            }
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=format_error_message(f"Session data is incomplete. Missing: {', '.join(missing_data)}. Please /start again.")
        )
        return ConversationHandler.END

    # Extract and validate data
    mother_wallet = session_data["mother_wallet"]
    child_wallets_data = session_data["child_wallets_data"]
    schedule = session_data["schedule"]
    token_address = session_data["token_address"]
    run_id = session_data["run_id"]

    await context.bot.send_message(
        chat_id=user_id,
        text="🚀 Initiating volume generation sequence...\n\n⏳ Preparing trade data..."
    )

    # Enhanced data preparation with validation
    try:
        child_wallets = [w.get('address') for w in child_wallets_data if w.get('address')]
        child_private_keys = [w.get('private_key') for w in child_wallets_data if w.get('private_key')]
        
        # Validate wallet data completeness
        if len(child_wallets) != len(child_private_keys):
            raise ValueError(f"Wallet data mismatch: {len(child_wallets)} addresses vs {len(child_private_keys)} private keys")
        
        if len(child_wallets) == 0:
            raise ValueError("No valid child wallets found")
        
        original_trades = schedule.get('transfers', [])
        if not original_trades:
            raise ValueError("No trades found in schedule")
        
        # Enhanced trade correction with validation
        corrected_trades = []
        invalid_trades = 0
        
        for i, trade in enumerate(original_trades):
            from_wallet = trade.get("from")
            to_wallet = trade.get("to") 
            amount = trade.get("amount")
            
            if from_wallet and to_wallet and amount and amount > 0:
                corrected_trades.append({
                    "from_wallet": from_wallet,
                    "to_wallet": to_wallet, 
                    "amount": float(amount)
                })
            else:
                invalid_trades += 1
                logger.warning(f"Invalid trade {i}: {trade}")
        
        if not corrected_trades:
            raise ValueError(f"No valid trades found. {invalid_trades} invalid trades detected.")
        
        logger.info(
            f"Volume generation data prepared",
            extra={
                "user_id": user_id,
                "run_id": run_id,
                "child_wallets_count": len(child_wallets),
                "valid_trades": len(corrected_trades),
                "invalid_trades": invalid_trades,
                "token_address": token_address
            }
        )
        
    except ValueError as e:
        logger.error(f"Data preparation failed for user {user_id}: {str(e)}")
        await context.bot.send_message(
            chat_id=user_id,
            text=format_error_message(f"Data preparation failed: {str(e)}. Please regenerate the schedule.")
        )
        return ConversationState.CHILD_BALANCES_OVERVIEW

    # Prepare job data with comprehensive information
    job_data = {
        'user_id': user_id,
        'mother_wallet': mother_wallet,
        'child_wallets': child_wallets,
        'child_private_keys': child_private_keys,
        'trades': corrected_trades,
        'token_address': token_address,
        'run_id': run_id,
        'job_created_at': time.time()
    }

    # Schedule the volume generation job
    try:
        job_name = f"vol_run_{user_id}_{int(time.time())}"
        context.job_queue.run_once(volume_generation_job, when=2, data=job_data, name=job_name)
        
        logger.info(
            f"Successfully scheduled volume generation job",
            extra={
                "user_id": user_id,
                "run_id": run_id,
                "job_name": job_name,
                "trades_count": len(corrected_trades),
                "child_wallets_count": len(child_wallets)
            }
        )
        
        # Send confirmation with progress tracking
        confirmation_message = (
            f"🚀 **SPL Volume Generation STARTED**\n\n"
            f"**Run ID:** `{run_id}`\n"
            f"**Trades Queued:** {len(corrected_trades)}\n"
            f"**Child Wallets:** {len(child_wallets)}\n"
            f"**SPL Token:** `{token_address[:8]}...{token_address[-8:]}`\n"
            f"**Job Name:** `{job_name}`\n\n"
            f"⏳ Your SPL volume run is executing in the background.\n"
            f"Transactions will start processing momentarily.\n"
            f"You will be notified when it completes."
        )
        
        await context.bot.send_message(
            chat_id=user_id,
            text=confirmation_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [build_button("📊 Check Progress (Coming Soon)", "check_progress")],
                [build_button("❌ Cancel Run (Not Available)", "abort_run")]
            ])
        )
        
        return ConversationState.EXECUTION
        
    except Exception as e:
        logger.error(
            f"Failed to schedule volume generation job",
            extra={
                "user_id": user_id,
                "run_id": run_id,
                "error": str(e)
            }
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=format_error_message(f"Failed to start volume generation: {str(e)}")
        )
        return ConversationState.CHILD_BALANCES_OVERVIEW


async def trigger_volume_generation(update: Update, context: CallbackContext) -> int:
    """Triggers the volume generation process by scheduling a background job with enhanced validation."""
    user = update.callback_query.from_user
    query = update.callback_query
    
    # Handle the callback query answer only if it's a real query
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Could not answer callback query: {e}")
    
    logger.info(f"🚀 TRIGGER_VOLUME_GENERATION called for user {user.id}")
    print(f"🚀 TRIGGER_VOLUME_GENERATION called for user {user.id}")  # Console output for immediate visibility

    # Enhanced session data retrieval with logging
    session_data = {
        "mother_wallet": session_manager.get_session_value(user.id, "mother_wallet"),
        "child_wallets_data": session_manager.get_session_value(user.id, "child_wallets_data"),
        "schedule": session_manager.get_session_value(user.id, "schedule"),
        "token_address": session_manager.get_session_value(user.id, "token_address"),
        "run_id": session_manager.get_session_value(user.id, "run_id")
    }

    # Comprehensive validation with detailed error reporting
    missing_data = [key for key, value in session_data.items() if not value]
    if missing_data:
        logger.error(
            f"Missing critical session data for volume generation",
            extra={
                "user_id": user.id,
                "missing_data": missing_data,
                "available_data": [key for key, value in session_data.items() if value]
            }
        )
        await query.edit_message_text(
            format_error_message(f"Session data is incomplete. Missing: {', '.join(missing_data)}. Please /start again.")
        )
        return ConversationHandler.END

    # Extract and validate data
    mother_wallet = session_data["mother_wallet"]
    child_wallets_data = session_data["child_wallets_data"]
    schedule = session_data["schedule"]
    token_address = session_data["token_address"]
    run_id = session_data["run_id"]

    await query.edit_message_text("🚀 Initiating volume generation sequence...\n\n⏳ Preparing trade data...")

    # Enhanced data preparation with validation
    try:
        child_wallets = [w.get('address') for w in child_wallets_data if w.get('address')]
        child_private_keys = [w.get('private_key') for w in child_wallets_data if w.get('private_key')]
        
        # Validate wallet data completeness
        if len(child_wallets) != len(child_private_keys):
            raise ValueError(f"Wallet data mismatch: {len(child_wallets)} addresses vs {len(child_private_keys)} private keys")
        
        if len(child_wallets) == 0:
            raise ValueError("No valid child wallets found")
        
        original_trades = schedule.get('transfers', [])
        if not original_trades:
            raise ValueError("No trades found in schedule")
        
        # Enhanced trade correction with validation
        corrected_trades = []
        invalid_trades = 0
        
        for i, trade in enumerate(original_trades):
            from_wallet = trade.get("from")
            to_wallet = trade.get("to") 
            amount = trade.get("amount")
            
            if from_wallet and to_wallet and amount and amount > 0:
                corrected_trades.append({
                    "from_wallet": from_wallet,
                    "to_wallet": to_wallet, 
                    "amount": float(amount)
                })
            else:
                invalid_trades += 1
                logger.warning(f"Invalid trade {i}: {trade}")
        
        if not corrected_trades:
            raise ValueError(f"No valid trades found. {invalid_trades} invalid trades detected.")
        
        logger.info(
            f"Volume generation data prepared",
            extra={
                "user_id": user.id,
                "run_id": run_id,
                "child_wallets_count": len(child_wallets),
                "valid_trades": len(corrected_trades),
                "invalid_trades": invalid_trades,
                "token_address": token_address
            }
        )
        
    except ValueError as e:
        logger.error(f"Data preparation failed for user {user.id}: {str(e)}")
        await query.edit_message_text(
            format_error_message(f"Data preparation failed: {str(e)}. Please regenerate the schedule.")
        )
        return ConversationState.CHILD_BALANCES_OVERVIEW

    # Prepare job data with comprehensive information
    job_data = {
        'user_id': user.id,
        'mother_wallet': mother_wallet,
        'child_wallets': child_wallets,
        'child_private_keys': child_private_keys,
        'trades': corrected_trades,
        'token_address': token_address,
        'run_id': run_id,
        'job_created_at': time.time()
    }

    # Schedule the volume generation job
    try:
        job_name = f"vol_run_{user.id}_{int(time.time())}"
        context.job_queue.run_once(volume_generation_job, when=2, data=job_data, name=job_name)
        
        logger.info(
            f"Successfully scheduled volume generation job",
            extra={
                "user_id": user.id,
                "run_id": run_id,
                "job_name": job_name,
                "trades_count": len(corrected_trades),
                "child_wallets_count": len(child_wallets)
            }
        )
        
        # Send confirmation with progress tracking
        confirmation_message = (
            f"🚀 **SPL Volume Generation STARTED**\n\n"
            f"**Run ID:** `{run_id}`\n"
            f"**Trades Queued:** {len(corrected_trades)}\n"
            f"**Child Wallets:** {len(child_wallets)}\n"
            f"**SPL Token:** `{token_address[:8]}...{token_address[-8:]}`\n"
            f"**Job Name:** `{job_name}`\n\n"
            f"⏳ Your SPL volume run is executing in the background.\n"
            f"Transactions will start processing momentarily.\n"
            f"You will be notified when it completes."
        )
        
        await context.bot.send_message(
            chat_id=user.id,
            text=confirmation_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [build_button("📊 Check Progress (Coming Soon)", "check_progress")],
                [build_button("❌ Cancel Run (Not Available)", "abort_run")]
            ])
        )
        
        return ConversationState.EXECUTION
        
    except Exception as e:
        logger.error(
            f"Failed to schedule volume generation job",
            extra={
                "user_id": user.id,
                "run_id": run_id,
                "error": str(e)
            }
        )
        await context.bot.send_message(
            chat_id=user.id,
            text=format_error_message(f"Failed to start volume generation: {str(e)}")
        )
        return ConversationState.CHILD_BALANCES_OVERVIEW


async def sell_remaining_balance(update: Update, context: CallbackContext) -> int:
    """
    Handler to sell remaining token balance from child wallets.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next conversation state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()
    
    try:
        # Get session data
        child_wallets_data = session_manager.get_session_value(user.id, "child_wallets_data", [])
        token_address = session_manager.get_session_value(user.id, "token_address")
        
        if not child_wallets_data:
            await context.bot.send_message(
                chat_id=user.id,
                text="❌ No child wallets found. Please start a new volume generation run.",
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationState.COMPLETION
        
        if not token_address:
            await context.bot.send_message(
                chat_id=user.id,
                text="❌ No token address found. Please start a new volume generation run.",
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationState.COMPLETION
        
        # Extract wallet addresses and private keys
        child_wallets = [wallet["address"] for wallet in child_wallets_data]
        child_private_keys = [wallet["private_key"] for wallet in child_wallets_data]
        
        # Send progress message
        progress_message = await context.bot.send_message(
            chat_id=user.id,
            text=f"🔄 **Selling Remaining Token Balance**\n\n"
                 f"**Token:** `{token_address[:8]}...{token_address[-8:] if len(token_address) > 16 else token_address}`\n"
                 f"**Wallets:** {len(child_wallets)}\n"
                 f"**Status:** Checking token balances...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Execute sell operation
        sell_results = await api_client.sell_remaining_token_balance(
            child_wallets=child_wallets,
            child_private_keys=child_private_keys,
            token_address=token_address
        )
        
        # Format results message using utility function
        results_message = format_sell_remaining_balance_summary(sell_results, token_address)
        
        # Update progress message with results
        await context.bot.edit_message_text(
            chat_id=user.id,
            message_id=progress_message.message_id,
            text=results_message,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Offer next steps
        await context.bot.send_message(
            chat_id=user.id,
            text="What would you like to do next?",
            reply_markup=InlineKeyboardMarkup([
                [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")],
                [build_button("🔄 Finish and Start New Run", "finish_and_restart")]
            ])
        )
        
        return ConversationState.COMPLETION
        
    except Exception as e:
        logger.error(
            f"Error in sell remaining balance for user {user.id}",
            extra={"user_id": user.id, "error": str(e)},
            exc_info=True
        )
        
        await context.bot.send_message(
            chat_id=user.id,
            text=f"❌ **Error Selling Tokens**\n\n"
                 f"An error occurred while selling remaining token balance:\n"
                 f"`{str(e)}`\n\n"
                 f"Please try again or start a new run.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.COMPLETION


async def trigger_return_all_funds(update: Update, context: CallbackContext) -> int:
    """Return all funds from child wallets to the mother wallet."""
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()

    progress_message = await query.edit_message_text("💸 **Fund Return Process Started**...", parse_mode=ParseMode.MARKDOWN)

    mother_wallet = session_manager.get_session_value(user.id, "mother_wallet")
    child_wallets_data = session_manager.get_session_value(user.id, "child_wallets_data")

    if not mother_wallet or not child_wallets_data:
        await progress_message.edit_text(format_error_message("Critical data missing. Please /start again."))
        return ConversationHandler.END

    return_results = []
    for i, child_data in enumerate(child_wallets_data):
        child_address, child_pk = child_data.get('address'), child_data.get('private_key')
        if not child_address or not child_pk:
            continue
        try:
            await progress_message.edit_text(f"💸 Returning funds from wallet {i+1}/{len(child_wallets_data)}...", parse_mode=ParseMode.MARKDOWN)
            res = await api_client.transfer_child_to_mother(child_address, child_pk, mother_wallet, amount=None, verify_transfer=False)
            return_results.append(res)
        except Exception as e:
            return_results.append({'child_address': child_address, 'status': 'failed', 'error': str(e)})
        await asyncio.sleep(0.5)

    summary_message = format_return_funds_summary(return_results, mother_wallet)
    await context.bot.send_message(chat_id=user.id, text=summary_message, parse_mode=ParseMode.MARKDOWN)
    session_manager.clear_session(user.id)
    await context.bot.send_message(user.id, "Operations complete. Type /start to begin a new session.")
    return ConversationHandler.END


async def finish_and_restart(update: Update, context: CallbackContext) -> int:
    """Ends the current flow and prompts the user to start a new one."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    session_manager.clear_session(user_id)
    
    await query.edit_message_text("Session cleared. Type /start to begin a new volume generation run.")
    
    return ConversationHandler.END


async def fund_child_wallets_handler(update: Update, context: CallbackContext) -> int:
    """Fund child wallets with the required amount for SPL swaps."""
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()

    # Get session data
    mother_wallet = session_manager.get_session_value(user.id, "mother_wallet")
    mother_private_key = session_manager.get_session_value(user.id, "mother_private_key")
    child_wallets = session_manager.get_session_value(user.id, "child_wallets")
    total_volume = session_manager.get_session_value(user.id, "total_volume")
    spl_readiness_check = session_manager.get_session_value(user.id, "spl_readiness_check", {})

    if not all([mother_wallet, mother_private_key, child_wallets, total_volume]):
        await query.edit_message_text(
            format_error_message("Session data missing. Please restart with /start.")
        )
        return ConversationHandler.END

    # Calculate funding amount per wallet
    min_required_per_wallet = spl_readiness_check.get('min_required_per_wallet', 0.0035)
    
    await query.edit_message_text(
        f"💰 **Funding Child Wallets**\n\n"
        f"Transferring {min_required_per_wallet:.6f} SOL to each child wallet...",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        # Fund child wallets using the existing API method
        funding_result = api_client.fund_child_wallets(
            mother_wallet=mother_wallet,
            child_wallets=child_wallets,
            token_address="So11111111111111111111111111111111111111112",  # SOL mint
            amount_per_wallet=min_required_per_wallet,
            mother_private_key=mother_private_key,
            verify_transfers=True
        )

        successful_transfers = funding_result.get("successful_transfers", 0)
        failed_transfers = funding_result.get("failed_transfers", 0)
        total_transfers = successful_transfers + failed_transfers

        logger.info(
            f"Child wallet funding completed for user {user.id}",
            extra={
                "user_id": user.id,
                "successful_transfers": successful_transfers,
                "failed_transfers": failed_transfers,
                "amount_per_wallet": min_required_per_wallet
            }
        )

        # Show funding results
        results_message = (
            f"💰 **Child Wallet Funding Complete**\n\n"
            f"✅ Successful: {successful_transfers}/{total_transfers}\n"
            f"❌ Failed: {failed_transfers}/{total_transfers}\n"
            f"💵 Amount per wallet: {min_required_per_wallet:.6f} SOL\n\n"
        )

        if failed_transfers == 0:
            results_message += "🎉 All wallets funded successfully! Ready for SPL volume generation."
            keyboard = [
                [build_button("🚀 Start SPL Volume Generation", "start_execution")],
                [build_button("🔄 Check Readiness Again", "check_spl_readiness")]
            ]
        else:
            results_message += f"⚠️ {failed_transfers} wallet(s) failed to fund. You can retry or proceed with ready wallets."
            keyboard = [
                [build_button("🔄 Retry Funding", "fund_child_wallets")],
                [build_button("🚀 Start with Ready Wallets", "start_execution")],
                [build_button("🔄 Check Readiness", "check_spl_readiness")]
            ]

        await context.bot.send_message(
            chat_id=user.id,
            text=results_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        # Update session to indicate funding completed
        session_manager.update_session_value(user.id, "child_wallets_need_funding", failed_transfers > 0)

        return ConversationState.PREVIEW_SCHEDULE

    except ApiClientError as e:
        logger.error(f"Error funding child wallets: {str(e)}", extra={"user_id": user.id})
        
        await context.bot.send_message(
            chat_id=user.id,
            text=format_error_message(f"Failed to fund child wallets: {str(e)}"),
            reply_markup=InlineKeyboardMarkup([
                [build_button("🔄 Try Again", "fund_child_wallets")],
                [build_button("🔄 Check Readiness", "check_spl_readiness")]
            ])
        )
        
        return ConversationState.PREVIEW_SCHEDULE


async def check_spl_readiness_handler(update: Update, context: CallbackContext) -> int:
    """Re-check SPL swap readiness for child wallets."""
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()

    # Get session data
    child_wallets = session_manager.get_session_value(user.id, "child_wallets")
    total_volume = session_manager.get_session_value(user.id, "total_volume")

    if not all([child_wallets, total_volume]):
        await query.edit_message_text(
            format_error_message("Session data missing. Please restart with /start.")
        )
        return ConversationHandler.END

    await query.edit_message_text("🔍 Rechecking SPL swap readiness...")

    try:
        # Calculate minimum swap amount
        min_swap_amount = total_volume / (len(child_wallets) * 10) if child_wallets else 0.0001
        
        # Check SPL swap readiness
        readiness_check = api_client.check_spl_swap_readiness(
            child_wallets=child_wallets,
            min_swap_amount_sol=min_swap_amount
        )

        # Update session with new readiness data
        session_manager.update_session_value(user.id, "spl_readiness_check", readiness_check)
        session_manager.update_session_value(user.id, "child_wallets_need_funding", readiness_check['status'] != 'ready')

        # Format readiness report
        readiness_message = (
            f"📊 **Updated SPL Swap Readiness Report**\n\n"
            f"**Status:** {readiness_check['status'].replace('_', ' ').title()}\n"
            f"**Ready Wallets:** {readiness_check['wallets_ready']}/{readiness_check['total_wallets']}\n"
            f"**Min Required per Wallet:** {readiness_check['min_required_per_wallet']:.6f} SOL\n"
            f"**Reserved for Fees/Rent:** {readiness_check['reserved_amount_per_wallet']:.6f} SOL\n\n"
        )
        
        for recommendation in readiness_check['recommendations']:
            readiness_message += f"{recommendation}\n"

        # Show appropriate buttons based on readiness status
        if readiness_check['status'] == 'ready':
            keyboard = [
                [build_button("🚀 Start SPL Volume Generation", "start_execution")],
                [build_button("💸 Return All Funds to Mother", "trigger_return_all_funds")]
            ]
            readiness_message += "\n🚀 All wallets ready for SPL volume generation!"
        elif readiness_check['status'] == 'partially_ready':
            keyboard = [
                [build_button("🚀 Start with Ready Wallets", "start_execution")],
                [build_button("💰 Fund Remaining Wallets", "fund_child_wallets")],
                [build_button("💸 Return All Funds", "trigger_return_all_funds")]
            ]
        else:
            keyboard = [
                [build_button("💰 Fund Child Wallets", "fund_child_wallets")],
                [build_button("🔄 Check Again", "check_spl_readiness")],
                [build_button("💸 Return All Funds", "trigger_return_all_funds")]
            ]

        await context.bot.send_message(
            chat_id=user.id,
            text=readiness_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return ConversationState.PREVIEW_SCHEDULE

    except ApiClientError as e:
        logger.error(f"Error checking SPL readiness: {str(e)}", extra={"user_id": user.id})
        
        await context.bot.send_message(
            chat_id=user.id,
            text=format_error_message(f"Failed to check readiness: {str(e)}"),
            reply_markup=InlineKeyboardMarkup([
                [build_button("🔄 Try Again", "check_spl_readiness")]
            ])
        )
        
        return ConversationState.PREVIEW_SCHEDULE


async def fund_more_wallets_handler(update: Update, context: CallbackContext) -> int:
    """Handler for funding more wallets when partially ready."""
    # This is essentially the same as fund_child_wallets_handler
    return await fund_child_wallets_handler(update, context)


def register_start_handler(application):
    """Register the start command handler."""
    # Import bundling handlers
    from bot.handlers.bundling_handler import (
        create_airdrop_wallet,
        import_airdrop_wallet,
        process_airdrop_wallet_import,
        bundled_wallets_count,
        token_creation_start,
        token_parameter_input,
        execute_token_creation,
        bundle_operation_progress
    )
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            # Activity Selection States
            ConversationState.ACTIVITY_SELECTION: [
                CallbackQueryHandler(activity_choice, pattern=r"^activity_"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.ACTIVITY_CONFIRMATION: [
                CallbackQueryHandler(start_volume_generation_workflow, pattern=f"^{CallbackPrefix.ACTIVITY}{CallbackPrefix.VOLUME_GENERATION}$"),
                CallbackQueryHandler(start_bundling_workflow, pattern=f"^{CallbackPrefix.ACTIVITY}{CallbackPrefix.BUNDLING}$")
            ],
            
            # Volume Generation States (existing)
            ConversationState.WALLET_CHOICE: [CallbackQueryHandler(wallet_choice)],
            ConversationState.IMPORT_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, import_wallet)],
            ConversationState.SAVED_WALLET_CHOICE: [CallbackQueryHandler(wallet_choice)],
            ConversationState.CHILD_WALLET_CHOICE: [CallbackQueryHandler(child_wallet_choice)],
            ConversationState.NUM_CHILD_WALLETS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, num_child_wallets),
                CallbackQueryHandler(num_child_wallets, pattern=r"^retry_wallets_")
            ],
            ConversationState.VOLUME_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, volume_amount)],
            ConversationState.TOKEN_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, token_address)],
            ConversationState.PREVIEW_SCHEDULE: [
                CallbackQueryHandler(check_balance, pattern=r"^check_balance$"),
                CallbackQueryHandler(start_execution, pattern=r"^start_execution$"),
                CallbackQueryHandler(trigger_return_all_funds, pattern=r"^trigger_return_all_funds$"),
                CallbackQueryHandler(regenerate_preview, pattern=r"^regenerate_preview$"),
                CallbackQueryHandler(fund_child_wallets_handler, pattern=r"^fund_child_wallets$"),
                CallbackQueryHandler(check_spl_readiness_handler, pattern=r"^check_spl_readiness$"),
                CallbackQueryHandler(fund_more_wallets_handler, pattern=r"^fund_more_wallets$")
            ],
            ConversationState.AWAIT_FUNDING: [
                CallbackQueryHandler(check_balance, pattern=r"^check_balance$"),
                CallbackQueryHandler(start_execution, pattern=r"^start_execution$"),
                CallbackQueryHandler(trigger_return_all_funds, pattern=r"^trigger_return_all_funds$"),
                CallbackQueryHandler(fund_child_wallets_handler, pattern=r"^fund_child_wallets$"),
                CallbackQueryHandler(check_spl_readiness_handler, pattern=r"^check_spl_readiness$")
            ],
            ConversationState.CHILD_BALANCES_OVERVIEW: [
                CallbackQueryHandler(trigger_volume_generation, pattern=r"^trigger_volume_generation$"),
                CallbackQueryHandler(trigger_return_all_funds, pattern=r"^trigger_return_all_funds$"),
                CallbackQueryHandler(child_balances_overview_handler, pattern=r"^retry_fetch_child_balances$")
            ],
            ConversationState.EXECUTION: [
                CallbackQueryHandler(cancel, pattern=r"^cancel$"),
                CallbackQueryHandler(sell_remaining_balance, pattern=r"^sell_remaining_balance$"),
                CallbackQueryHandler(trigger_return_all_funds, pattern=r"^trigger_return_all_funds$"),
                CallbackQueryHandler(finish_and_restart, pattern=r"^finish_and_restart$"),
            ],
            ConversationState.COMPLETION: [
                CallbackQueryHandler(sell_remaining_balance, pattern=r"^sell_remaining_balance$"),
                CallbackQueryHandler(trigger_return_all_funds, pattern=r"^trigger_return_all_funds$"),
                CallbackQueryHandler(finish_and_restart, pattern=r"^finish_and_restart$"),
            ],
            
            # Bundling Workflow States (NEW)
            ConversationState.BUNDLING_WALLET_SETUP: [
                CallbackQueryHandler(create_airdrop_wallet, pattern=r"^create_airdrop_wallet$"),
                CallbackQueryHandler(import_airdrop_wallet, pattern=r"^import_airdrop_wallet$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.IMPORT_AIRDROP_WALLET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_airdrop_wallet_import),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.BUNDLED_WALLETS_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bundled_wallets_count),
                CallbackQueryHandler(token_creation_start, pattern=r"^continue_to_bundled_count$"),
                CallbackQueryHandler(token_creation_start, pattern=r"^start_token_creation$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.TOKEN_CREATION_START: [
                CallbackQueryHandler(token_creation_start, pattern=r"^start_token_creation$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.TOKEN_PARAMETER_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, token_parameter_input),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.TOKEN_CREATION_PREVIEW: [
                CallbackQueryHandler(execute_token_creation, pattern=r"^confirm_token_creation$"),
                CallbackQueryHandler(token_creation_start, pattern=r"^edit_token_parameters$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.TOKEN_CREATION_EXECUTION: [
                CallbackQueryHandler(bundle_operation_progress, pattern=r"^execute_token_creation$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.BUNDLE_OPERATION_PROGRESS: [
                CallbackQueryHandler(bundle_operation_progress, pattern=r"^start_bundle_operations$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.BUNDLE_OPERATION_COMPLETE: [
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$"),
                CallbackQueryHandler(bundle_operation_progress, pattern=r"^view_transaction_details$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=CONVERSATION_TIMEOUT,
        name="start_conversation",
        persistent=False
    )
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('timeout', timeout_handler))