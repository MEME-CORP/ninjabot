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
    format_sell_remaining_balance_summary,
    format_activity_selection_message,
    format_activity_confirmation_message,
    format_bundler_management_selection_message
)
from bot.api.api_client import api_client, ApiClientError
from bot.events.event_system import event_system, TransactionConfirmedEvent, TransactionFailedEvent
from bot.utils.balance_poller import balance_poller
from bot.state.session_manager import session_manager
from bot.utils.wallet_storage import airdrop_wallet_storage, volume_wallet_storage


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
        [build_button("🚀 Token Bundling (PumpFun)", f"{CallbackPrefix.ACTIVITY}{CallbackPrefix.BUNDLING}")],
        [build_button("🎛️ Bundler Management", f"{CallbackPrefix.ACTIVITY}{CallbackPrefix.BUNDLER_MANAGEMENT}")]
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
    
    elif choice == f"{CallbackPrefix.ACTIVITY}{CallbackPrefix.BUNDLER_MANAGEMENT}":
        # User selected Bundler Management
        session_manager.update_session_value(user.id, "activity_type", "bundler_management")
        
        logger.info(
            f"User {user.id} selected Bundler Management",
            extra={"user_id": user.id, "activity": "bundler_management"}
        )
        
        # Redirect to bundler management workflow
        return await start_bundler_management_workflow(update, context)
    
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


# =====================
# Volume wallet handlers
# =====================

async def wallet_choice(update: Update, context: CallbackContext) -> int:
    """Handle wallet choice callbacks in WALLET_CHOICE state."""
    query = update.callback_query
    user = query.from_user
    await query.answer()

    data = query.data
    if data == "back_to_activities":
        return await start(update, context)

    if data == "create_wallet":
        # Create mother wallet via API and save
        try:
            await query.edit_message_text("🔄 Creating mother wallet...", parse_mode=ParseMode.MARKDOWN)
            wallet_info = api_client.create_wallet()
            address = wallet_info.get("address") or wallet_info.get("motherWalletPublicKey")
            if not address:
                raise ApiClientError("Wallet address missing from API response")

            # Persist to volume storage (mirror airdrop style)
            try:
                volume_wallet_storage.save_mother_wallet(user.id, {
                    "address": address,
                    "private_key": wallet_info.get("private_key") or wallet_info.get("motherWalletPrivateKeyBase58", ""),
                })
            except Exception as e:
                logger.warning(f"Failed to persist mother wallet file: {e}")

            # Show success
            await query.edit_message_text(
                format_wallet_created_message(address),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[build_button("→ Derive Child Wallets", "derive_children")], [build_button("« Back", "back_to_activities")]])
            )

            # Stash in session
            session_manager.update_session_value(user.id, "mother_wallet_address", address)
            session_manager.update_session_value(user.id, "mother_private_key", wallet_info.get("private_key") or wallet_info.get("motherWalletPrivateKeyBase58", ""))

            return ConversationState.WALLET_CHOICE
        except Exception as e:
            logger.error(f"Mother wallet creation failed: {e}")
            await query.edit_message_text(
                format_error_message(str(e)),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[build_button("« Back", "back_to_activities")]])
            )
            return ConversationState.WALLET_CHOICE

    if data == "import_wallet":
        await query.edit_message_text(
            "🔐 Send your mother wallet private key (Base58).",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[build_button("« Back", "back_to_activities")]])
        )
        return ConversationState.IMPORT_WALLET

    if data == "use_saved_wallet":
        saved = volume_wallet_storage.list_user_mother_wallets(user.id)
        if not saved:
            # fallback to API client's generic storage if any
            saved = api_client.list_saved_wallets('mother')
        if not saved:
            await query.edit_message_text(
                "📭 No saved mother wallets found.",
                reply_markup=InlineKeyboardMarkup([[build_button("« Back", "back_to_activities")]])
            )
            return ConversationState.WALLET_CHOICE

        # Build a simple selection menu
        buttons = []
        for w in saved[:10]:
            addr = w.get("address") or w.get("publicKey") or "unknown"
            label = f"{addr[:6]}...{addr[-6:]}"
            buttons.append([build_button(label, f"select_saved_{addr}")])
        buttons.append([build_button("« Back", "back_to_activities")])
        await query.edit_message_text("Select a saved mother wallet:", reply_markup=InlineKeyboardMarkup(buttons))
        return ConversationState.SAVED_WALLET_CHOICE

    if data == "derive_children":
        # Ask for number of child wallets
        await query.edit_message_text(
            "How many child wallets do you want to derive? (min 10)",
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.NUM_CHILD_WALLETS

    # Unknown callback in this state
    return ConversationState.WALLET_CHOICE


async def import_wallet_text(update: Update, context: CallbackContext) -> int:
    """Handle text input for importing a mother wallet by private key."""
    message = update.effective_message
    user = update.effective_user
    private_key = message.text.strip()
    try:
        await message.reply_text("🔄 Importing wallet...", parse_mode=ParseMode.MARKDOWN)
        wallet_info = api_client.import_wallet(private_key)
        address = wallet_info.get("address") or wallet_info.get("motherWalletPublicKey")
        if not address:
            raise ApiClientError("Failed to import wallet: address missing")

        # Persist
        try:
            volume_wallet_storage.save_mother_wallet(user.id, {
                "address": address,
                "private_key": private_key,
                "imported": True,
            })
        except Exception as e:
            logger.warning(f"Failed to persist imported mother wallet: {e}")

        # Session
        session_manager.update_session_value(user.id, "mother_wallet_address", address)
        session_manager.update_session_value(user.id, "mother_private_key", private_key)

        await message.reply_text(
            format_wallet_imported_message(address),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[build_button("→ Derive Child Wallets", "derive_children")], [build_button("« Back", "back_to_activities")]])
        )
        return ConversationState.WALLET_CHOICE
    except Exception as e:
        logger.error(f"Wallet import failed: {e}")
        await message.reply_text(format_error_message(str(e)), parse_mode=ParseMode.MARKDOWN)
        return ConversationState.IMPORT_WALLET


async def saved_wallet_choice(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    user = query.from_user
    await query.answer()
    data = query.data
    if data.startswith("select_saved_"):
        addr = data.replace("select_saved_", "")
        session_manager.update_session_value(user.id, "mother_wallet_address", addr)
        await query.edit_message_text(
            f"Selected mother wallet: `{addr}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[build_button("→ Derive Child Wallets", "derive_children")], [build_button("« Back", "back_to_activities")]])
        )
        return ConversationState.WALLET_CHOICE
    return ConversationState.SAVED_WALLET_CHOICE


async def num_child_wallets(update: Update, context: CallbackContext) -> int:
    message = update.effective_message
    user = update.effective_user
    text = message.text.strip()
    try:
        # validate_child_wallets_input returns (is_valid, value_or_error)
        is_valid, value_or_error = validate_child_wallets_input(text)
        # Log with correct parameter order: (type, input_value, is_valid, error_message, user_id)
        log_validation_result("num_child_wallets", text, is_valid, None if is_valid else value_or_error, user.id)
        if not is_valid:
            await message.reply_text(value_or_error or "Invalid number. Enter a number ≥ 10.")
            return ConversationState.NUM_CHILD_WALLETS

        mother = session_manager.get_session_value(user.id, "mother_wallet_address")
        if not mother:
            await message.reply_text("Mother wallet missing. Please create/import first.")
            return ConversationState.WALLET_CHOICE

        await message.reply_text("🔄 Deriving child wallets...", parse_mode=ParseMode.MARKDOWN)
        # value_or_error is guaranteed to be the parsed int when is_valid is True
        children = api_client.derive_child_wallets(value_or_error, mother)

        # Persist
        try:
            volume_wallet_storage.save_child_wallets(user.id, mother, children)
        except Exception as e:
            logger.warning(f"Failed to persist child wallets: {e}")

        # Prepare summary
        child_addresses = [c.get('address') for c in children if isinstance(c, dict)]
        if not child_addresses:
            child_addresses = [c for c in children if isinstance(c, str)]

        await message.reply_text(
            format_child_wallets_message(len(child_addresses), child_addresses[:10]),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.VOLUME_AMOUNT
    except Exception as e:
        logger.error(f"Deriving child wallets failed: {e}")
        await message.reply_text(format_error_message(str(e)), parse_mode=ParseMode.MARKDOWN)
        return ConversationState.NUM_CHILD_WALLETS


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
    
    # Check if user has existing airdrop wallets
    existing_wallets = airdrop_wallet_storage.list_user_airdrop_wallets(user.id)
    
    # Build keyboard for airdrop wallet setup
    keyboard = [
        [build_button("Create Airdrop Wallet", "create_airdrop_wallet")],
        [build_button("Import Airdrop Wallet", "import_airdrop_wallet")]
    ]
    
    # Add option to use existing wallet if available
    if existing_wallets:
        keyboard.insert(1, [build_button("Use Existing Airdrop Wallet", "use_existing_airdrop_wallet")])
    
    keyboard.append([build_button("« Back to Activities", "back_to_activities")])

    message_text = "🏪 **Airdrop Wallet Setup**\n\n"
    message_text += "First, let's set up your airdrop (mother) wallet that will fund your bundled wallets.\n\n"
    
    if existing_wallets:
        message_text += f"💡 Found {len(existing_wallets)} existing airdrop wallet(s) for your account.\n\n"
    
    message_text += "Choose how you want to set up your airdrop wallet:"

    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

    return ConversationState.BUNDLING_WALLET_SETUP


async def start_bundler_management_workflow(update: Update, context: CallbackContext) -> int:
    """
    Start the bundler management workflow for token management.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    
    # Import token storage
    from bot.utils.token_storage import token_storage
    from bot.utils.message_utils import format_bundler_management_selection_message, format_token_list_message
    
    # Get user's created tokens
    user_tokens = token_storage.get_user_tokens(user.id)
    
    if not user_tokens:
        # No tokens found, show message and redirect back
        keyboard = [[build_button("« Back to Activities", "back_to_activities")]]
        
        await query.edit_message_text(
            "📭 **No Tokens Found**\n\n"
            "You haven't created any tokens yet.\n\n"
            "Use 'Token Bundling (PumpFun)' to create your first token!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.ACTIVITY_SELECTION
    
    # Show bundler management selection
    keyboard = [
        [build_button("📋 View Created Tokens", "view_tokens")],
        [build_button("« Back to Activities", "back_to_activities")]
    ]
    
    await query.edit_message_text(
        format_bundler_management_selection_message(),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.BUNDLER_MANAGEMENT


def register_start_handler(application):
    """
    Register the start handler with minimal bundler management integration.
    
    This preserves existing working code while adding bundler management.
    """
    from telegram.ext import ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
    from bot.handlers.token_trading_handler import (
        bundler_management_choice,
        show_token_list,
        token_selection,
        token_operation_choice,
        back_to_token_options,
        sell_percentage_choice,
        sell_confirmation_choice,
        airdrop_wallet_selection_choice,
        wallet_balance_overview_choice
    )
    
    # Import the bundling handlers
    from bot.handlers.wallet_handler import (
        create_airdrop_wallet,
        wait_and_retry_airdrop,
        import_airdrop_wallet,
        process_airdrop_wallet_import,
        continue_to_bundled_wallets_setup,
        bundled_wallets_count,
        check_wallet_balance,
        fund_bundled_wallets_now,
        start_wallet_funding,
        retry_wallet_funding,
        return_funds_confirmation,
        execute_return_funds,
        return_funds_complete,
        use_existing_airdrop_wallet,
        select_existing_airdrop_wallet
    )
    
    # Import the token creation handlers
    from bot.handlers.bundling_handler import (
        token_creation_start,
        configure_buy_amounts,
        start_buy_amounts_input,
        buy_amounts_input,
        edit_buy_amounts
    )
    
    # Import the token config handlers
    from bot.handlers.token_config_handler import (
        token_parameter_input,
        process_token_image_upload,
        skip_image_upload,
        proceed_to_preview,
        edit_token_parameters
    )
    
    # Import the token creation final handler
    from bot.handlers.token_creation_handler import (
        back_to_token_preview,
        create_token_final
    )

    # Simple conversation handler for essential functionality including bundling workflow
    conversation_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ConversationState.ACTIVITY_SELECTION: [
                CallbackQueryHandler(activity_choice, pattern=r"^activity_"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.WALLET_CHOICE: [
                CallbackQueryHandler(wallet_choice),
            ],
            ConversationState.IMPORT_WALLET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, import_wallet_text),
                CallbackQueryHandler(wallet_choice, pattern=r"^back_to_activities$"),
            ],
            ConversationState.SAVED_WALLET_CHOICE: [
                CallbackQueryHandler(saved_wallet_choice),
            ],
            ConversationState.NUM_CHILD_WALLETS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, num_child_wallets),
            ],
            ConversationState.BUNDLER_MANAGEMENT: [
                CallbackQueryHandler(bundler_management_choice)
            ],
            ConversationState.AIRDROP_WALLET_SELECTION: [
                CallbackQueryHandler(airdrop_wallet_selection_choice)
            ],
            ConversationState.WALLET_BALANCE_OVERVIEW: [
                CallbackQueryHandler(wallet_balance_overview_choice)
            ],
            ConversationState.TOKEN_LIST: [
                CallbackQueryHandler(token_selection)
            ],
            ConversationState.TOKEN_MANAGEMENT_OPTIONS: [
                CallbackQueryHandler(token_operation_choice),
                CallbackQueryHandler(token_creation_start, pattern=r"^start_token_creation$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.TOKEN_TRADING_OPERATION: [
                CallbackQueryHandler(back_to_token_options, pattern=r"^back_to_token_options$")
            ],
            ConversationState.SELL_PERCENTAGE_SELECTION: [
                CallbackQueryHandler(sell_percentage_choice)
            ],
            ConversationState.SELL_CONFIRM_EXECUTE: [
                CallbackQueryHandler(sell_confirmation_choice)
            ],
            # Bundling workflow states
            ConversationState.BUNDLING_WALLET_SETUP: [
                CallbackQueryHandler(create_airdrop_wallet, pattern=r"^create_airdrop_wallet$"),
                CallbackQueryHandler(wait_and_retry_airdrop, pattern=r"^wait_and_retry_airdrop$"),
                CallbackQueryHandler(import_airdrop_wallet, pattern=r"^import_airdrop_wallet$"),
                CallbackQueryHandler(use_existing_airdrop_wallet, pattern=r"^use_existing_airdrop_wallet$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.IMPORT_AIRDROP_WALLET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_airdrop_wallet_import),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.SELECT_EXISTING_AIRDROP_WALLET: [
                CallbackQueryHandler(select_existing_airdrop_wallet, pattern=r"^select_airdrop_"),
                CallbackQueryHandler(start_bundling_workflow, pattern=r"^back_to_bundling_setup$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.BUNDLED_WALLETS_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bundled_wallets_count),
                CallbackQueryHandler(continue_to_bundled_wallets_setup, pattern=r"^continue_to_bundled_count$"),
                CallbackQueryHandler(token_creation_start, pattern=r"^start_token_creation$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.WALLET_BALANCE_CHECK: [
                CallbackQueryHandler(check_wallet_balance, pattern=r"^check_wallet_balance$"),
                CallbackQueryHandler(fund_bundled_wallets_now, pattern=r"^fund_bundled_wallets_now$"),
                CallbackQueryHandler(return_funds_confirmation, pattern=r"^return_funds_confirmation$"),
                CallbackQueryHandler(token_creation_start, pattern=r"^start_token_creation$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.WALLET_FUNDING_REQUIRED: [
                CallbackQueryHandler(start_wallet_funding, pattern=r"^start_wallet_funding$"),
                CallbackQueryHandler(check_wallet_balance, pattern=r"^check_wallet_balance$"),
                CallbackQueryHandler(return_funds_confirmation, pattern=r"^return_funds_confirmation$"),
                CallbackQueryHandler(edit_buy_amounts, pattern=r"^edit_buy_amounts$")
            ],
            ConversationState.WALLET_FUNDING_PROGRESS: [
                CallbackQueryHandler(check_wallet_balance, pattern=r"^check_wallet_balance$"),
                CallbackQueryHandler(return_funds_confirmation, pattern=r"^return_funds_confirmation$"),
                CallbackQueryHandler(create_token_final, pattern=r"^create_token_final$")
            ],
            # Add missing TOKEN_CREATION_START state
            ConversationState.TOKEN_CREATION_START: [
                CallbackQueryHandler(token_creation_start, pattern=r"^start_token_creation$"),
                CallbackQueryHandler(create_token_final, pattern=r"^create_token_final$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            # Token creation workflow states
            ConversationState.TOKEN_PARAMETER_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, token_parameter_input),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.TOKEN_IMAGE_UPLOAD: [
                MessageHandler(filters.PHOTO, process_token_image_upload),
                CallbackQueryHandler(skip_image_upload, pattern=r"^skip_image$"),
                CallbackQueryHandler(proceed_to_preview, pattern=r"^proceed_to_preview$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.TOKEN_CREATION_PREVIEW: [
                CallbackQueryHandler(configure_buy_amounts, pattern=r"^configure_buy_amounts$"),
                CallbackQueryHandler(edit_token_parameters, pattern=r"^edit_token_parameters$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.BUY_AMOUNTS_CONFIG: [
                CallbackQueryHandler(start_buy_amounts_input, pattern=r"^start_buy_amounts_input$"),
                CallbackQueryHandler(back_to_token_preview, pattern=r"^back_to_token_preview$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.BUY_AMOUNTS_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, buy_amounts_input),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            ConversationState.BUY_AMOUNTS_PREVIEW: [
                CallbackQueryHandler(check_wallet_balance, pattern=r"^check_wallet_balance$"),
                CallbackQueryHandler(edit_buy_amounts, pattern=r"^edit_buy_amounts$"),
                CallbackQueryHandler(activity_choice, pattern=r"^back_to_activities$")
            ],
            # Return funds workflow states
            ConversationState.RETURN_FUNDS_CONFIRMATION: [
                CallbackQueryHandler(execute_return_funds, pattern=r"^execute_return_funds$"),
                CallbackQueryHandler(check_wallet_balance, pattern=r"^check_wallet_balance$"),
                CallbackQueryHandler(edit_buy_amounts, pattern=r"^edit_buy_amounts$")
            ],
            ConversationState.RETURN_FUNDS_COMPLETE: [
                CallbackQueryHandler(check_wallet_balance, pattern=r"^check_wallet_balance$"),
                CallbackQueryHandler(create_token_final, pattern=r"^create_token_final$")
            ]
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )
    
    application.add_handler(conversation_handler)
    logger.info("Start handler with bundler management registered successfully")