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

            # Stash in session first
            session_manager.update_session_value(user.id, "mother_wallet_address", address)
            session_manager.update_session_value(user.id, "mother_private_key", wallet_info.get("private_key") or wallet_info.get("motherWalletPrivateKeyBase58", ""))

            # Check for existing child wallets for this mother wallet
            existing_sets = volume_wallet_storage.list_user_child_wallet_sets(user.id)
            matching_set = None
            for s in existing_sets:
                if s.get("mother_address") == address and s.get("wallets"):
                    matching_set = s
                    break  # sets are sorted newest-first

            if matching_set:
                child_wallets = [w.get("address") for w in matching_set.get("wallets", []) if w.get("address")]
                if child_wallets:
                    # Populate session so we can skip derivation
                    session_manager.update_session_value(user.id, "child_wallets", child_wallets)
                    session_manager.update_session_value(user.id, "num_child_wallets", len(child_wallets))

                    summary_text = (
                        f"✅ Created mother wallet: `{address}`\n\n"
                        f"🔁 Found {len(child_wallets)} existing child wallets for this address.\n\n"
                        f"You can proceed by entering the total volume you want to generate (in SOL).\n"
                        f"If you prefer to derive a fresh set, tap the button below." 
                    )

                    await query.edit_message_text(
                        summary_text,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=InlineKeyboardMarkup([
                            [build_button("↺ Derive New Child Wallets", "derive_children")],
                            [build_button("« Back", "back_to_activities")]
                        ])
                    )

                    # Prompt for volume amount
                    await context.bot.send_message(
                        chat_id=user.id,
                        text="Enter the total volume you want to generate (in SOL, e.g. 0.5 or 1.2):",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return ConversationState.VOLUME_AMOUNT

            # No existing child wallets found, show derive option
            await query.edit_message_text(
                format_wallet_created_message(address),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[build_button("→ Derive Child Wallets", "derive_children")], [build_button("« Back", "back_to_activities")]])
            )

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

        # Check for existing child wallets for this imported wallet
        existing_sets = volume_wallet_storage.list_user_child_wallet_sets(user.id)
        matching_set = None
        for s in existing_sets:
            if s.get("mother_address") == address and s.get("wallets"):
                matching_set = s
                break  # sets are sorted newest-first

        if matching_set:
            child_wallets = [w.get("address") for w in matching_set.get("wallets", []) if w.get("address")]
            if child_wallets:
                # Populate session so we can skip derivation
                session_manager.update_session_value(user.id, "child_wallets", child_wallets)
                session_manager.update_session_value(user.id, "num_child_wallets", len(child_wallets))

                summary_text = (
                    f"✅ Imported mother wallet: `{address}`\n\n"
                    f"🔁 Found {len(child_wallets)} existing child wallets for this address.\n\n"
                    f"You can proceed by entering the total volume you want to generate (in SOL).\n"
                    f"If you prefer to derive a fresh set, tap the button below." 
                )

                await message.reply_text(
                    summary_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([
                        [build_button("↺ Derive New Child Wallets", "derive_children")],
                        [build_button("« Back", "back_to_activities")]
                    ])
                )

                # Prompt for volume amount
                await message.reply_text(
                    "Enter the total volume you want to generate (in SOL, e.g. 0.5 or 1.2):",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ConversationState.VOLUME_AMOUNT

        # No existing child wallets found, show derive option
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
        
        # Load the complete wallet data from saved wallets to get private key
        saved_wallets = api_client.list_saved_wallets('mother')
        selected_wallet = None
        for wallet in saved_wallets:
            if wallet.get('address') == addr:
                selected_wallet = wallet
                break
        
        if not selected_wallet:
            await query.edit_message_text(
                format_error_message("Selected wallet not found in saved data."),
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationState.WALLET_CHOICE
        
        # Store both address and private key in session
        session_manager.update_session_value(user.id, "mother_wallet_address", addr)
        private_key = selected_wallet.get('private_key', '')
        if private_key:
            session_manager.update_session_value(user.id, "mother_private_key", private_key)
            logger.info(f"Loaded mother wallet with private key for user {user.id}: {addr[:8]}...")
        else:
            logger.warning(f"No private key found for selected wallet {addr[:8]}... for user {user.id}")

        # Attempt to locate existing child wallet set for this mother wallet
        existing_sets = volume_wallet_storage.list_user_child_wallet_sets(user.id)
        matching_set = None
        for s in existing_sets:
            if s.get("mother_address") == addr and s.get("wallets"):
                matching_set = s
                break  # sets are sorted newest-first

        if matching_set:
            child_wallets = [w.get("address") for w in matching_set.get("wallets", []) if w.get("address")]
            if child_wallets:
                # Populate session so we can skip derivation
                session_manager.update_session_value(user.id, "child_wallets", child_wallets)
                session_manager.update_session_value(user.id, "num_child_wallets", len(child_wallets))

                summary_text = (
                    f"✅ Selected mother wallet: `{addr}`\n\n"
                    f"🔁 Reusing {len(child_wallets)} existing child wallets.\n\n"
                    f"You can proceed by entering the total volume you want to generate (in SOL).\n"
                    f"If you prefer to derive a fresh set, tap the button below." 
                )

                try:
                    await query.edit_message_text(
                        summary_text,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=InlineKeyboardMarkup([
                            [build_button("↺ Derive New Child Wallets", "derive_children")],
                            [build_button("« Back", "back_to_activities")]
                        ])
                    )
                except Exception:
                    await context.bot.send_message(
                        chat_id=user.id,
                        text=summary_text,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=InlineKeyboardMarkup([
                            [build_button("↺ Derive New Child Wallets", "derive_children")],
                            [build_button("« Back", "back_to_activities")]
                        ])
                    )

                # Prompt for volume amount
                await context.bot.send_message(
                    chat_id=user.id,
                    text="Enter the total volume you want to generate (in SOL, e.g. 0.5 or 1.2):",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ConversationState.VOLUME_AMOUNT

        # Fallback: no existing child wallets, keep original derive prompt
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

        # Store in session for subsequent steps - STORE FULL WALLET DATA
        session_manager.update_session_value(user.id, "child_wallets", child_addresses)
        session_manager.update_session_value(user.id, "child_wallets_full", children)  # Store full wallet data with private keys
        session_manager.update_session_value(user.id, "num_child_wallets", len(child_addresses))

        await message.reply_text(
            format_child_wallets_message(len(child_addresses), child_addresses[:10]),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.VOLUME_AMOUNT
    except Exception as e:
        logger.error(f"Deriving child wallets failed: {e}")
        await message.reply_text(format_error_message(str(e)), parse_mode=ParseMode.MARKDOWN)
        return ConversationState.NUM_CHILD_WALLETS
async def volume_amount(update: Update, context: CallbackContext) -> int:
    """Handle the volume amount input for volume generation."""
    user = update.effective_user
    text = update.message.text.strip()
    is_valid, value_or_error = validate_volume_input(text)
    # Log validation
    log_validation_result("volume_amount", text, is_valid, None if is_valid else value_or_error, user.id)
    if not is_valid:
        await update.message.reply_text(format_error_message(value_or_error), parse_mode=ParseMode.MARKDOWN)
        return ConversationState.VOLUME_AMOUNT

    # Persist chosen volume
    total_volume = value_or_error
    session_manager.update_session_value(user.id, "total_volume", total_volume)

    # Confirm and prompt for token address (CA)
    await update.message.reply_text(
        format_volume_confirmation_message(total_volume),
        parse_mode=ParseMode.MARKDOWN
    )
    await update.message.reply_text(
        "Please paste the token Contract Address (CA) to continue.",
        parse_mode=ParseMode.MARKDOWN
    )

    return ConversationState.TOKEN_ADDRESS


async def token_address(update: Update, context: CallbackContext) -> int:
    """Handle token address input for volume generation."""
    user = update.effective_user
    text = update.message.text.strip()
    is_valid, value_or_error = validate_token_address(text)
    log_validation_result("token_address", text, is_valid, None if is_valid else value_or_error, user.id)
    if not is_valid:
        await update.message.reply_text(format_error_message(value_or_error), parse_mode=ParseMode.MARKDOWN)
        return ConversationState.TOKEN_ADDRESS

    token_addr = value_or_error
    session_manager.update_session_value(user.id, "token_address", token_addr)

    # Defensive: ensure prerequisites exist before preview
    mother_wallet = (
        session_manager.get_session_value(user.id, "mother_wallet_address")
        or session_manager.get_session_value(user.id, "mother_wallet")
    )
    child_wallets = session_manager.get_session_value(user.id, "child_wallets") or []
    total_volume = session_manager.get_session_value(user.id, "total_volume")
    if not mother_wallet or not child_wallets or not total_volume:
        await update.message.reply_text(
            format_error_message("Missing setup data (wallets/volume). Please restart with /start."),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.ACTIVITY_SELECTION

    # Generate preview and start balance monitoring prompt
    await generate_preview(update, context)
    return ConversationState.PREVIEW_SCHEDULE


async def generate_preview(update: Update, context: CallbackContext) -> None:
    """Generate and show schedule preview for volume generation."""
    user = update.effective_user
    mother_wallet = (
        session_manager.get_session_value(user.id, "mother_wallet_address")
        or session_manager.get_session_value(user.id, "mother_wallet")
    )
    child_wallets = session_manager.get_session_value(user.id, "child_wallets") or []
    token_addr = session_manager.get_session_value(user.id, "token_address")
    total_volume = session_manager.get_session_value(user.id, "total_volume")
    num_child = session_manager.get_session_value(user.id, "num_child_wallets") or len(child_wallets)

    # Show loading message
    message = await context.bot.send_message(chat_id=user.id, text="Generating transfer schedule...")

    try:
        schedule = api_client.generate_schedule(
            mother_wallet=mother_wallet,
            child_wallets=child_wallets,
            token_address=token_addr,
            total_volume=total_volume,
        )
        # Persist in session
        session_manager.update_session_value(user.id, "schedule", schedule)
        session_manager.update_session_value(user.id, "run_id", schedule.get("run_id"))

        preview_text = format_schedule_preview(
            schedule=schedule.get("transfers", []),
            total_volume=total_volume,
            token_address=token_addr,
            num_child_wallets=num_child,
            mother_wallet_address=mother_wallet or ""
        )
        await message.edit_text(preview_text, parse_mode=ParseMode.MARKDOWN)

        # Add balance check prompt
        await context.bot.send_message(
            chat_id=user.id,
            text="Please fund the wallet now. I'll check the balance every few seconds.",
            reply_markup=InlineKeyboardMarkup([[build_button("Check Balance Now", "check_balance")]])
        )

        # Start polling in background
        await start_balance_polling(user.id, context)
    except Exception as e:
        logger.error(f"Error generating schedule preview: {e}")
        await message.edit_text(
            format_error_message(f"Could not generate schedule: {str(e)}"),
            parse_mode=ParseMode.MARKDOWN
        )


async def start_balance_polling(user_id: int, context: CallbackContext) -> None:
    """Start polling for mother wallet balance until target reached."""
    mother_wallet = (
        session_manager.get_session_value(user_id, "mother_wallet_address")
        or session_manager.get_session_value(user_id, "mother_wallet")
    )
    # Always poll SOL balance for funding readiness; token CA is not used for polling
    token_addr = None
    total_volume = session_manager.get_session_value(user_id, "total_volume")

    if not all([mother_wallet, total_volume]):
        logger.error("Missing session data for balance polling", extra={"user_id": user_id})
        return

    async def on_target_reached():
        balance_info = api_client.check_balance(mother_wallet, token_addr)
        current_balance = 0
        token_symbol = "tokens"
        if isinstance(balance_info, dict) and 'balances' in balance_info:
            for tb in balance_info['balances']:
                if tb.get('symbol') == 'SOL' or tb.get('token') == "So11111111111111111111111111111111111111112":
                    current_balance = tb.get('amount', 0)
                    token_symbol = tb.get('symbol', 'SOL')
                    break
        # Always present unified post-balance action buttons so user can continue
        action_keyboard = InlineKeyboardMarkup([
            [build_button("🔍 Check Child Wallets", "check_child_balances")],
            [build_button("🚀 Begin Transfers", "begin_transfers")],
            [build_button("💸 Return All Funds", "trigger_return_all_funds")]
        ])
        await context.bot.send_message(
            chat_id=user_id,
            text=format_sufficient_balance_message(balance=current_balance, token_symbol=token_symbol),
            reply_markup=action_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    await balance_poller.start_polling(
        wallet_address=mother_wallet,
    token_address=token_addr,  # None => SOL balance
        target_balance=total_volume,
        on_target_reached=on_target_reached
    )

    logger.info(
        "Started balance polling",
        extra={"user_id": user_id, "wallet": mother_wallet, "target": total_volume}
    )


async def check_balance(update: Update, context: CallbackContext) -> int:
    """Manually check mother wallet balance against target."""
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()

    mother_wallet = (
        session_manager.get_session_value(user.id, "mother_wallet_address")
        or session_manager.get_session_value(user.id, "mother_wallet")
    )
    token_addr = session_manager.get_session_value(user.id, "token_address")
    total_volume = session_manager.get_session_value(user.id, "total_volume")

    if not all([mother_wallet, token_addr, total_volume]):
        await query.edit_message_text(
            format_error_message("Session data missing. Please restart with /start."),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.ACTIVITY_SELECTION

    try:
        try:
            await query.edit_message_text(
                f"Checking balance for wallet: `{mother_wallet[:8]}...{mother_wallet[-8:]}`...",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass

        # Check if balance poller is already running to avoid double requests
        poller_task_id = f"{mother_wallet}_{token_addr or 'So11111111111111111111111111111111111111112'}"
        if poller_task_id in balance_poller._polling_tasks and poller_task_id in balance_poller._last_balances:
            # Use cached balance from poller to avoid duplicate API call
            logger.info(f"Using cached balance from poller for {mother_wallet[:8]}...")
            current_balance = balance_poller._last_balances[poller_task_id]
            token_symbol = "SOL"
        else:
            # Only make API call if poller is not active
            logger.info(f"Making direct balance check for {mother_wallet[:8]}...")
            balance_info = api_client.check_balance(mother_wallet, token_addr)
            current_balance = 0
            token_symbol = "tokens"
            if isinstance(balance_info, dict) and 'balances' in balance_info:
                for tb in balance_info['balances']:
                    if tb.get('symbol') == 'SOL' or tb.get('token') == "So11111111111111111111111111111111111111112":
                        current_balance = tb.get('amount', 0)
                        token_symbol = tb.get('symbol', 'SOL')
                        break
        # Use either cached poller balance or direct API result above; no duplicate re-parsing

        if current_balance >= total_volume:
            # Provide consistent action buttons when balance is sufficient
            action_keyboard = InlineKeyboardMarkup([
                [build_button("🔍 Check Child Wallets", "check_child_balances")],
                [build_button("🚀 Begin Transfers", "begin_transfers")],
                [build_button("💸 Return All Funds", "trigger_return_all_funds")]
            ])
            try:
                await query.edit_message_text(
                    format_sufficient_balance_message(balance=current_balance, token_symbol=token_symbol),
                    reply_markup=action_keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                # Fallback send if edit fails (e.g., message too old)
                await context.bot.send_message(
                    chat_id=user.id,
                    text=format_sufficient_balance_message(balance=current_balance, token_symbol=token_symbol),
                    reply_markup=action_keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            # Build keyboard with both check again and return funds options
            balance_keyboard = [
                [build_button("Check Again", "check_balance")],
                [build_button("💰 Return Funds from Child Wallets", "return_child_funds")]
            ]
            
            await query.edit_message_text(
                format_insufficient_balance_message(current_balance=current_balance, required_balance=total_volume, token_symbol=token_symbol),
                reply_markup=InlineKeyboardMarkup(balance_keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        return ConversationState.AWAIT_FUNDING
    except Exception as e:
        logger.error(f"Error checking balance: {e}")
        await query.edit_message_text(
            format_error_message(f"Could not check balance: {str(e)}"),
            reply_markup=InlineKeyboardMarkup([[build_button("Try Again", "check_balance")]]),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.AWAIT_FUNDING


async def check_child_wallets_balances_handler(update: Update, context: CallbackContext) -> int:
    """Check child wallet balances and determine funding needs."""
    query = update.callback_query
    user = query.from_user
    await query.answer()

    # Get session data
    child_wallets = session_manager.get_session_value(user.id, "child_wallets") or []
    total_volume = session_manager.get_session_value(user.id, "total_volume") or 0.01
    
    if not child_wallets:
        await query.edit_message_text(
            format_error_message("No child wallets found. Please start the setup process again."),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.PREVIEW_SCHEDULE

    # Calculate minimum balance threshold (base volume per wallet + gas reserve)
    base_amount_per_wallet = total_volume / len(child_wallets)
    gas_reserve = 0.0015
    min_balance_threshold = base_amount_per_wallet + gas_reserve

    await query.edit_message_text(
        "⏳ **Checking Child Wallet Balances**\n\n"
        f"Analyzing {len(child_wallets)} child wallets...\n"
        f"Minimum required balance: {min_balance_threshold:.4f} SOL per wallet",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        # Check child wallet balances
        balance_check = api_client.check_child_wallets_balances(
            child_wallets=child_wallets,
            min_balance_threshold=min_balance_threshold
        )

        if balance_check.get('status') != 'success':
            error_msg = balance_check.get('message', 'Unknown error occurred during balance check')
            await context.bot.send_message(
                chat_id=user.id,
                text=format_error_message(f"Balance check failed: {error_msg}"),
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationState.PREVIEW_SCHEDULE

        # Store balance check results in session
        session_manager.update_session_value(user.id, "child_balance_check", balance_check)
        
        # Generate response message and keyboard based on results
        message_text, keyboard = _format_balance_check_results(balance_check)
        
        await context.bot.send_message(
            chat_id=user.id,
            text=message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

        return ConversationState.AWAIT_FUNDING

    except Exception as e:
        logger.error(f"Child wallet balance check failed for user {user.id}: {e}")
        await context.bot.send_message(
            chat_id=user.id,
            text=format_error_message(f"Failed to check child wallet balances: {str(e)}"),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.PREVIEW_SCHEDULE


def _format_balance_check_results(balance_check: Dict[str, Any]) -> tuple:
    """Format balance check results into message text and keyboard."""
    total_wallets = balance_check['total_wallets']
    funded_wallets = balance_check['funded_wallets']
    unfunded_wallets = balance_check['unfunded_wallets']
    total_existing_balance = balance_check['total_existing_balance']
    total_funding_needed = balance_check['total_funding_needed']
    recommendation = balance_check['recommendation']
    
    # Build status message
    status_lines = [
        "💰 **Child Wallet Balance Check Complete**\n",
        f"📊 **Summary:**",
        f"• Total wallets: {total_wallets}",
        f"• Already funded: {funded_wallets}",
        f"• Need funding: {unfunded_wallets}",
        f"• Existing balance: {total_existing_balance:.4f} SOL",
    ]
    
    if total_funding_needed > 0:
        status_lines.append(f"• Funding needed: {total_funding_needed:.4f} SOL")
    
    status_lines.extend([
        "",
        f"💡 **Recommendation:** {recommendation['message']}"
    ])
    
    # Build detailed wallet list if partially funded
    if balance_check['partially_funded']:
        status_lines.extend([
            "",
            "📋 **Wallet Details:**"
        ])
        
        for wallet_info in balance_check['wallet_details']:
            address = wallet_info['address']
            balance = wallet_info['balance_sol']
            is_funded = wallet_info['is_funded']
            status_emoji = "✅" if is_funded else "❌"
            status_lines.append(f"{status_emoji} `{address[:8]}...` - {balance:.4f} SOL")

    message_text = "\n".join(status_lines)
    
    # Build keyboard based on recommendation
    keyboard = []
    
    if recommendation['action'] == 'skip_funding':
        # All wallets funded - go straight to volume generation
        keyboard = [
            [build_button("🚀 Start Volume Generation", "start_execution")],
            [build_button("🔄 Recheck Balances", "check_child_balances")],
            [build_button("⚙️ View Details", "show_wallet_details")]
        ]
    elif recommendation['action'] == 'selective_funding':
        # Some wallets funded - offer selective funding
        keyboard = [
            [build_button(recommendation['button_text'], "fund_unfunded_wallets")],
            [build_button("💰 Fund All Wallets Anyway", "fund_all_wallets")],
            [build_button("🚀 Start with Funded Wallets", "start_execution")],
            [build_button("🔄 Recheck Balances", "check_child_balances")]
        ]
    else:
        # No wallets funded - require full funding
        keyboard = [
            [build_button(recommendation['button_text'], "fund_child_wallets")],
            [build_button("🔄 Recheck Balances", "check_child_balances")],
            [build_button("⚙️ View Details", "show_wallet_details")]
        ]
    
    # Add return button
    keyboard.append([build_button("« Back", "regenerate_preview")])
    
    return message_text, keyboard


async def show_wallet_details_handler(update: Update, context: CallbackContext) -> int:
    """Show detailed information about child wallet balances."""
    query = update.callback_query
    user = query.from_user
    await query.answer()

    # Get balance check results from session
    balance_check = session_manager.get_session_value(user.id, "child_balance_check")
    
    if not balance_check:
        await query.edit_message_text(
            format_error_message("Balance check data not found. Please check balances again."),
            reply_markup=InlineKeyboardMarkup([[build_button("🔄 Check Balances", "check_child_balances")]]),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.AWAIT_FUNDING

    # Build detailed wallet information
    detail_lines = [
        "📋 **Child Wallet Details**\n",
        f"**Summary:**",
        f"• Total wallets: {balance_check['total_wallets']}",
        f"• Already funded: {balance_check['funded_wallets']}",
        f"• Need funding: {balance_check['unfunded_wallets']}",
        f"• Total balance: {balance_check['total_existing_balance']:.4f} SOL",
        ""
    ]

    if balance_check['total_funding_needed'] > 0:
        detail_lines.append(f"• Additional funding needed: {balance_check['total_funding_needed']:.4f} SOL")
        detail_lines.append("")

    detail_lines.append("**Individual Wallets:**")
    
    for wallet_info in balance_check['wallet_details']:
        address = wallet_info['address']
        balance = wallet_info['balance_sol']
        is_funded = wallet_info['is_funded']
        min_required = wallet_info['min_balance_threshold']
        
        status_emoji = "✅" if is_funded else "❌"
        status_text = "Funded" if is_funded else "Needs funding"
        
        detail_lines.append(
            f"{status_emoji} `{address[:8]}...{address[-8:]}`\n"
            f"   Balance: {balance:.4f} SOL | Required: {min_required:.4f} SOL\n"
            f"   Status: {status_text}"
        )

    message_text = "\n".join(detail_lines)
    
    # Build keyboard
    keyboard = [
        [build_button("🔄 Recheck Balances", "check_child_balances")],
        [build_button("« Back", "check_child_balances")]
    ]
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.AWAIT_FUNDING


async def begin_transfers(update: Update, context: CallbackContext) -> int:
    """Entry point after sufficient balance. Placeholder to proceed to child funding/execution.

    Currently just acknowledges and would be extended to invoke funding logic.
    """
    query = update.callback_query
    await query.answer()
    user = query.from_user

    # Log the current conversation state for debugging
    logger.info(f"begin_transfers called for user {user.id}")

    # Fetch session data
    mother_wallet = (
        session_manager.get_session_value(user.id, "mother_wallet_address")
        or session_manager.get_session_value(user.id, "mother_wallet")
    )
    child_wallets = session_manager.get_session_value(user.id, "child_wallets") or []
    total_volume = session_manager.get_session_value(user.id, "total_volume")
    mother_private_key = session_manager.get_session_value(user.id, "mother_private_key")

    # Instrumentation (Systematic Isolation / Boundary Verification)
    logger.info(
        "Begin transfers invoked",
        extra={
            "user_id": user.id,
            "mother_wallet_present": bool(mother_wallet),
            "child_wallets_count": len(child_wallets),
            "total_volume": total_volume,
            "mother_private_key_present": bool(mother_private_key),
        }
    )

    if not all([mother_wallet, child_wallets, total_volume]):
        await query.edit_message_text(
            format_error_message("Missing session data for transfers. Please /start again."),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.ACTIVITY_SELECTION

    if not mother_private_key:
        # Provide explicit guidance instead of silently failing later
        await query.edit_message_text(
            format_error_message(
                "Mother wallet private key not found in session. Import or create the mother wallet again to proceed."
            ),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.ACTIVITY_SELECTION

    # Immediately proceed to funding child wallets (minimal integration)
    await query.edit_message_text(
        "💰 Preparing to fund child wallets...",
        parse_mode=ParseMode.MARKDOWN
    )

    return await fund_child_wallets_handler(update, context)


async def return_child_funds_handler(update: Update, context: CallbackContext) -> int:
    """
    Handle return funds request from child wallets back to mother wallet.
    """
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    try:
        # Get session data
        logger.info(f"Return funds handler called for user {user.id}")
        mother_wallet = session_manager.get_session_value(user.id, "mother_wallet_address") or \
                       session_manager.get_session_value(user.id, "mother_wallet")
        
        logger.info(f"Mother wallet found: {mother_wallet}")
        
        if not mother_wallet:
            logger.warning(f"No mother wallet found for user {user.id}")
            await query.edit_message_text(
                format_error_message("No mother wallet found. Please start over."),
                reply_markup=InlineKeyboardMarkup([[build_button("« Start Over", "back_to_activities")]]),
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationState.ACTIVITY_SELECTION
        
        # Load child wallets with private keys
        logger.info(f"Loading child wallets for mother wallet {mother_wallet}")
        child_wallets_full = api_client.load_child_wallets(mother_wallet)
        logger.info(f"Found {len(child_wallets_full) if child_wallets_full else 0} child wallets")
        
        if not child_wallets_full:
            logger.warning(f"No child wallets found for mother wallet {mother_wallet}")
            await query.edit_message_text(
                format_error_message("No child wallets found. Create child wallets first."),
                reply_markup=InlineKeyboardMarkup([[build_button("🔍 Check Balance", "check_balance")]]),
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationState.AWAIT_FUNDING
        
        # Show confirmation message with return funds progress
        await query.edit_message_text(
            f"🔄 **Returning Funds from Child Wallets**\n\n"
            f"Processing {len(child_wallets_full)} child wallets...\n"
            f"Returning all available funds to mother wallet.\n\n"
            f"This may take a few minutes. Please wait...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Execute return funds operation
        results = []
        successful = 0
        failed = 0
        
        for child_wallet_data in child_wallets_full:
            try:
                child_wallet = child_wallet_data.get('address')
                child_private_key = child_wallet_data.get('private_key')
                
                if not child_wallet or not child_private_key:
                    failed += 1
                    results.append({
                        "wallet": child_wallet or "Unknown",
                        "status": "failed",
                        "error": "Missing wallet data or private key"
                    })
                    continue
                
                # Use the existing transfer function to return funds (amount=0 means return all)
                logger.info(f"Attempting to return funds from child wallet {child_wallet} to mother wallet {mother_wallet}")
                result = await api_client.transfer_child_to_mother(
                    child_wallet=child_wallet,
                    child_private_key=child_private_key,
                    mother_wallet=mother_wallet,
                    amount=0,  # Return all available funds
                    verify_transfer=True
                )
                logger.info(f"Return funds result for {child_wallet}: {result}")
                
                if result.get("status") == "success":
                    successful += 1
                    results.append({
                        "wallet": child_wallet,
                        "status": "success",
                        "amount": result.get("amount_transferred", 0)
                    })
                else:
                    failed += 1
                    results.append({
                        "wallet": child_wallet,
                        "status": "failed",
                        "error": result.get("error", "Unknown error")
                    })
                    
            except Exception as e:
                logger.error(f"Error returning funds from {child_wallet_data.get('address', 'Unknown')}: {e}")
                failed += 1
                results.append({
                    "wallet": child_wallet_data.get('address', 'Unknown'),
                    "status": "failed",
                    "error": str(e)
                })
        
        # Show results and return to balance check
        result_message = format_return_funds_summary(results, mother_wallet)
        result_message += f"\n\n✅ Successfully returned funds from {successful} wallets"
        if failed > 0:
            result_message += f"\n❌ Failed to return funds from {failed} wallets"
        
        result_message += f"\n\nYou can now check your balance again."
        
        await query.edit_message_text(
            result_message,
            reply_markup=InlineKeyboardMarkup([[build_button("🔍 Check Balance Again", "check_balance")]]),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ConversationState.AWAIT_FUNDING
    except Exception as e:
        logger.error(f"Error in return_child_funds_handler: {e}")
        await query.edit_message_text(
            format_error_message(f"Error returning funds: {str(e)}"),
            reply_markup=InlineKeyboardMarkup([
                [build_button("🔍 Check Balance", "check_balance")],
                [build_button("« Back", "back_to_activities")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.AWAIT_FUNDING

async def trigger_return_all_funds(update: Update, context: CallbackContext) -> int:
    """Callback alias for returning all child wallet funds to mother wallet.

    This exists because keyboards use callback_data 'trigger_return_all_funds'.
    Previously no handler was registered, so button clicks were no-ops. This
    function simply delegates to return_child_funds_handler to preserve a
    single implementation point.
    """
    logger.info("trigger_return_all_funds callback invoked – delegating to return_child_funds_handler")
    return await return_child_funds_handler(update, context)


async def fund_child_wallets_handler(update: Update, context: CallbackContext) -> int:
    """Fund child wallets with required SOL for subsequent SPL volume generation.

    Defensive: handles session key variants (mother_wallet_address vs mother_wallet) and
    normalizes funding_result schema differences.
    """
    query = update.callback_query
    user = query.from_user
    # Only answer if coming from a callback (may be invoked directly by begin_transfers)
    try:
        await query.answer()
    except Exception:
        pass

    # Retrieve session data with fallbacks
    mother_wallet = (
        session_manager.get_session_value(user.id, "mother_wallet_address")
        or session_manager.get_session_value(user.id, "mother_wallet")
    )
    mother_private_key = session_manager.get_session_value(user.id, "mother_private_key")
    child_wallets = session_manager.get_session_value(user.id, "child_wallets") or []
    total_volume = session_manager.get_session_value(user.id, "total_volume")

    if not all([mother_wallet, mother_private_key, child_wallets, total_volume]):
        await context.bot.send_message(
            chat_id=user.id,
            text=format_error_message("Missing session data for funding. Please /start again."),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.AWAIT_FUNDING

    # Calculate funding amount per wallet based on total volume
    # Total volume should be distributed among child wallets for volume generation
    base_amount_per_wallet = total_volume / len(child_wallets)
    
    # Add small buffer for gas fees (0.0015 SOL should be sufficient for multiple transactions)
    gas_reserve = 0.0015
    min_required_per_wallet = base_amount_per_wallet + gas_reserve
    
    logger.info(f"Funding calculation: total_volume={total_volume}, child_wallets={len(child_wallets)}, "
                f"base_per_wallet={base_amount_per_wallet}, gas_reserve={gas_reserve}, "
                f"final_per_wallet={min_required_per_wallet}")
    
    # Debug: Log the actual child wallets format
    logger.info(f"Child wallets format: {type(child_wallets)}, sample: {child_wallets[:2] if len(child_wallets) >= 2 else child_wallets}")
    
    # Attempt readiness check with the calculated amount
    try:
        readiness = api_client.check_spl_swap_readiness(child_wallets=child_wallets, min_swap_amount_sol=base_amount_per_wallet)
        session_manager.update_session_value(user.id, "spl_readiness_check", readiness)
        logger.info(f"SPL readiness check result: {readiness}")
    except Exception as e:
        logger.warning(f"Readiness check failed prior to funding: {e}")

    await context.bot.send_message(
        chat_id=user.id,
        text=(
            "� **Funding Child Wallets**\n\n"
            f"Transferring ~{min_required_per_wallet:.6f} SOL to each of {len(child_wallets)} child wallets..."
        ),
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        logger.info(f"Calling api_client.fund_child_wallets with:")
        logger.info(f"  - mother_wallet: {mother_wallet}")
        logger.info(f"  - child_wallets (count): {len(child_wallets)}")
        logger.info(f"  - token_address: So11111111111111111111111111111111111111112")
        logger.info(f"  - amount_per_wallet: {min_required_per_wallet}")
        logger.info(f"  - verify_transfers: True")
        
        funding_result = api_client.fund_child_wallets(
            mother_wallet=mother_wallet,
            child_wallets=child_wallets,
            token_address="So11111111111111111111111111111111111111112",  # SOL mint
            amount_per_wallet=min_required_per_wallet,
            mother_private_key=mother_private_key,
            verify_transfers=True
        )
        
        logger.info(f"Funding result received: {funding_result}")

        # Normalize result fields
        successful_transfers = funding_result.get("successful_transfers")
        failed_transfers = funding_result.get("failed_transfers")

        # If absent, infer from other hints
        if successful_transfers is None:
            if isinstance(funding_result.get("api_response"), dict):
                api_resp = funding_result["api_response"]
                successful_transfers = (
                    api_resp.get("successful_transfers")
                    or api_resp.get("funded_wallets")
                    or len(api_resp.get("transactions", []))
                )
            else:
                successful_transfers = funding_result.get("funded_wallets") or 0
        if failed_transfers is None:
            failed_transfers = funding_result.get("failed_wallets") or 0

        total_transfers = successful_transfers + failed_transfers

        logger.info(
            "Child wallet funding completed",
            extra={
                "user_id": user.id,
                "mother_wallet": mother_wallet,
                "successful_transfers": successful_transfers,
                "failed_transfers": failed_transfers,
                "keys": list(funding_result.keys())
            }
        )

        summary_lines = [
            "💰 **Child Wallet Funding Complete**\n",
            f"✅ Successful: {successful_transfers}/{total_transfers}",
            f"❌ Failed: {failed_transfers}/{total_transfers}",
            f"💵 Amount per wallet: {min_required_per_wallet:.6f} SOL\n"
        ]

        if failed_transfers == 0:
            summary_lines.append("🎉 All wallets funded successfully! Ready for SPL volume generation.")
            keyboard = [
                [build_button("🚀 Start SPL Volume Generation", "start_execution")],
                [build_button("🔄 Check Readiness Again", "check_balance")],
            ]
        else:
            summary_lines.append("⚠️ Some wallets failed to fund. You can retry or proceed with funded wallets.")
            keyboard = [
                [build_button("🔄 Retry Funding", "fund_child_wallets")],
                [build_button("🚀 Start with Ready Wallets", "start_execution")],
                [build_button("🔄 Recheck Balance", "check_balance")]
            ]

        await context.bot.send_message(
            chat_id=user.id,
            text="\n".join(summary_lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        # Track if additional funding needed
        session_manager.update_session_value(user.id, "child_wallets_need_funding", failed_transfers > 0)
        # Persist chosen amount per wallet for reference
        session_manager.update_session_value(user.id, "funding_amount_per_wallet", min_required_per_wallet)

        return ConversationState.AWAIT_FUNDING
    except ApiClientError as e:
        logger.error(f"Funding API error: {e}")
        await context.bot.send_message(
            chat_id=user.id,
            text=format_error_message(f"Funding failed: {str(e)}"),
            reply_markup=InlineKeyboardMarkup([[build_button("Try Again", "fund_child_wallets")]])
        )
        return ConversationState.AWAIT_FUNDING


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
    await query.answer()

    # Initialize PumpFun client (was previously unreachable due to misplaced code)
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

async def regenerate_preview(update: Update, context: CallbackContext) -> int:
    """Regenerate the schedule preview upon user request."""
    query = update.callback_query
    await query.answer()
    await generate_preview(update, context)
    return ConversationState.PREVIEW_SCHEDULE


async def start_bundler_management_workflow(update: Update, context: CallbackContext) -> int:
    """
    Start the bundler management workflow.
    
    Args:
        update: The update object
        context: The context object
        
    Returns:
        The next state
    """
    user = update.callback_query.from_user
    query = update.callback_query
    await query.answer()

    # Build the bundler management keyboard
    keyboard = [
        [build_button("📊 Token List & Trading", f"{CallbackPrefix.TOKEN_TRADING}")],
        [build_button("💼 Airdrop Wallet Selection", f"{CallbackPrefix.AIRDROP_WALLET_SELECTION}")],
        [build_button("💰 Wallet Balance Overview", f"{CallbackPrefix.WALLET_BALANCE_OVERVIEW}")],
        [build_button("« Back to Activities", "back_to_activities")]
    ]

    await query.edit_message_text(
        format_bundler_management_selection_message(),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationState.BUNDLER_MANAGEMENT


async def start_spl_volume_execution(update: Update, context: CallbackContext) -> int:
    """Handle the start of SPL volume execution after child wallets are funded."""
    query = update.callback_query
    user = query.from_user
    await query.answer()

    # Get session data with comprehensive logging
    mother_wallet = (
        session_manager.get_session_value(user.id, "mother_wallet_address")
        or session_manager.get_session_value(user.id, "mother_wallet")
    )
    child_wallets = session_manager.get_session_value(user.id, "child_wallets") or []
    child_wallets_full = session_manager.get_session_value(user.id, "child_wallets_full") or []
    token_address = session_manager.get_session_value(user.id, "token_address")
    total_volume = session_manager.get_session_value(user.id, "total_volume")
    schedule = session_manager.get_session_value(user.id, "schedule")
    
    # Enhanced logging for debugging
    logger.info(f"SPL Volume Execution Debug - User {user.id}:")
    logger.info(f"  - mother_wallet: {mother_wallet}")
    logger.info(f"  - child_wallets count: {len(child_wallets) if child_wallets else 0}")
    logger.info(f"  - child_wallets_full count: {len(child_wallets_full) if child_wallets_full else 0}")
    logger.info(f"  - token_address: {token_address}")
    logger.info(f"  - total_volume: {total_volume}")
    logger.info(f"  - schedule: {bool(schedule)}")

    # Try to recover missing data if child_wallets_full is empty but child_wallets exists
    if child_wallets and not child_wallets_full:
        logger.warning(f"Attempting to recover child_wallets_full data for user {user.id}")
        try:
            # Load child wallets from API client saved data
            if mother_wallet:
                recovered_child_wallets = api_client.load_child_wallets(mother_wallet)
                if recovered_child_wallets:
                    child_wallets_full = recovered_child_wallets
                    session_manager.update_session_value(user.id, "child_wallets_full", child_wallets_full)
                    logger.info(f"Recovered {len(child_wallets_full)} child wallets with private keys")
        except Exception as e:
            logger.error(f"Failed to recover child wallets: {str(e)}")

    # Generate mock schedule if missing but we have other data
    if not schedule and child_wallets and token_address and total_volume:
        logger.warning(f"Generating mock schedule for user {user.id}")
        try:
            # Create a simple mock schedule using API client's generate_schedule
            mock_schedule = api_client.generate_schedule(
                mother_wallet=mother_wallet,
                child_wallets=child_wallets,
                token_address=token_address,
                total_volume=total_volume
            )
            schedule = mock_schedule
            session_manager.update_session_value(user.id, "schedule", schedule)
            logger.info(f"Generated mock schedule with {len(schedule.get('transfers', []))} transfers")
        except Exception as e:
            logger.error(f"Failed to generate mock schedule: {str(e)}")

    # Check critical requirements
    if not all([mother_wallet, child_wallets, token_address, total_volume]):
        missing_items = []
        if not mother_wallet: missing_items.append("mother_wallet")
        if not child_wallets: missing_items.append("child_wallets") 
        if not token_address: missing_items.append("token_address")
        if not total_volume: missing_items.append("total_volume")
        
        error_msg = f"Missing required data: {', '.join(missing_items)}. Please start over."
        logger.error(f"SPL Volume execution failed for user {user.id}: {error_msg}")
        
        await query.edit_message_text(
            format_error_message(error_msg),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.AWAIT_FUNDING

    # Extract trades from schedule and prepare child wallet private keys
    trades = schedule.get("transfers", []) if schedule else []
    if not trades:
        # Generate simple mock trades if none available
        logger.warning(f"No trades in schedule, generating simple mock trades for user {user.id}")
        import random
        num_trades = min(len(child_wallets) * 2, 10)  # Max 10 trades
        trades = []
        for i in range(num_trades):
            sender_idx = i % len(child_wallets)
            receiver_idx = (i + 1) % len(child_wallets)
            trade_amount = total_volume / num_trades  # Distribute total volume
            trades.append({
                "from": child_wallets[sender_idx],
                "to": child_wallets[receiver_idx],
                "amount": trade_amount,
                "wallet_index": sender_idx
            })

    # Handle child wallet private keys
    child_private_keys = []
    if child_wallets_full:
        child_private_keys = [
            wallet.get("private_key", wallet.get("privateKeyBase58", "")) 
            for wallet in child_wallets_full
        ]
    
    # If we don't have private keys, try alternative approach
    if not child_private_keys or any(not key for key in child_private_keys):
        logger.warning(f"Missing or incomplete private keys for user {user.id}, attempting recovery")
        # Try to load from mother wallet private key and derive child keys
        mother_private_key = session_manager.get_session_value(user.id, "mother_wallet_private_key")
        if mother_private_key and child_wallets:
            try:
                # Re-derive child wallets with private keys
                logger.info(f"Re-deriving child wallets for user {user.id}")
                full_child_wallets = api_client.derive_child_wallets(
                    n=len(child_wallets),
                    mother_wallet=mother_wallet
                )
                if full_child_wallets and len(full_child_wallets) >= len(child_wallets):
                    child_wallets_full = full_child_wallets
                    child_private_keys = [
                        wallet.get("private_key", wallet.get("privateKeyBase58", "")) 
                        for wallet in child_wallets_full
                    ]
                    # Update session with recovered data
                    session_manager.update_session_value(user.id, "child_wallets_full", child_wallets_full)
                    logger.info(f"Successfully re-derived {len(child_private_keys)} child wallet private keys")
            except Exception as e:
                logger.error(f"Failed to re-derive child wallets: {str(e)}")
    
    # Final validation for private keys
    if not child_private_keys or any(not key for key in child_private_keys):
        error_msg = "Missing child wallet private keys. Please regenerate child wallets."
        logger.error(f"SPL Volume execution failed for user {user.id}: {error_msg}")
        
        await query.edit_message_text(
            format_error_message(error_msg),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationState.AWAIT_FUNDING

    # Start the volume generation process
    await query.edit_message_text(
        "🚀 **Starting SPL Volume Generation**\n\n"
        f"Token: `{token_address}`\n"
        f"Total Volume: {total_volume} SOL\n"
        f"Child Wallets: {len(child_wallets)}\n"
        f"Trades Planned: {len(trades)}\n\n"
        "⏳ Initializing volume generation...",
        parse_mode=ParseMode.MARKDOWN
    )

    # Generate a run ID for this execution
    import uuid
    run_id = f"spl_volume_{user.id}_{int(time.time())}"
    session_manager.update_session_value(user.id, "current_run_id", run_id)

    # Comprehensive logging before job start
    logger.info(f"Starting volume generation job for user {user.id}")
    logger.info(f"Job data validation:")
    logger.info(f"  - run_id: {run_id}")
    logger.info(f"  - mother_wallet: {mother_wallet}")
    logger.info(f"  - child_wallets: {len(child_wallets)}")
    logger.info(f"  - child_private_keys: {len(child_private_keys)}")
    logger.info(f"  - token_address: {token_address}")
    logger.info(f"  - total_volume: {total_volume}")
    logger.info(f"  - trades: {len(trades)}")

    # Start the volume generation job in the background
    from bot.handlers.start_handler import volume_generation_job
    context.job_queue.run_once(
        volume_generation_job,
        when=1,  # Start in 1 second
        data={
            'user_id': user.id,
            'run_id': run_id,
            'mother_wallet': mother_wallet,
            'child_wallets': child_wallets,
            'child_private_keys': child_private_keys,  
            'token_address': token_address,
            'total_volume': total_volume,
            'trades': trades,  
            'schedule': schedule
        },
        name=f"volume_job_{user.id}"
    )

    logger.info(f"✅ Successfully started volume generation job for user {user.id} with run_id {run_id}")
    
    # Return to a waiting state while the job runs
    return ConversationState.AWAIT_FUNDING


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
            ConversationState.VOLUME_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, volume_amount),
            ],
            ConversationState.TOKEN_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, token_address),
            ],
            ConversationState.PREVIEW_SCHEDULE: [
                CallbackQueryHandler(check_balance, pattern=r"^check_balance$"),
                CallbackQueryHandler(check_child_wallets_balances_handler, pattern=r"^check_child_balances$"),
                CallbackQueryHandler(regenerate_preview, pattern=r"^regenerate_preview$"),
                CallbackQueryHandler(begin_transfers, pattern=r"^begin_transfers$"),
                CallbackQueryHandler(trigger_return_all_funds, pattern=r"^trigger_return_all_funds$")
            ],
            ConversationState.AWAIT_FUNDING: [
                CallbackQueryHandler(check_balance, pattern=r"^check_balance$"),
                CallbackQueryHandler(check_child_wallets_balances_handler, pattern=r"^check_child_balances$"),
                CallbackQueryHandler(show_wallet_details_handler, pattern=r"^show_wallet_details$"),
                CallbackQueryHandler(return_child_funds_handler, pattern=r"^return_child_funds$"),
                CallbackQueryHandler(trigger_return_all_funds, pattern=r"^trigger_return_all_funds$"),
                CallbackQueryHandler(begin_transfers, pattern=r"^begin_transfers$"),
                CallbackQueryHandler(fund_child_wallets_handler, pattern=r"^fund_child_wallets$"),
                CallbackQueryHandler(fund_child_wallets_handler, pattern=r"^fund_unfunded_wallets$"),
                CallbackQueryHandler(fund_child_wallets_handler, pattern=r"^fund_all_wallets$"),
                CallbackQueryHandler(start_spl_volume_execution, pattern=r"^start_execution$")
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