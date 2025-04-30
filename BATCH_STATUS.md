# Solana Volume Bot - Batch Completion Status

This file tracks the completion status of the project batches based on the current codebase.

**Legend:**
- `[x]` Done
- `[ ]` Undone

---

## Batch 1: core_essential_interface

**Status:** Mostly Done (Frontend Interface)

*   `[x]` Present /start wizard (wallet creation/connection, N wallets, total volume, token address).
    *   _Notes: Implemented in `start_handler.py` covering `ConversationState` steps from START to TOKEN_ADDRESS._
*   `[x]` Render preview schedule, display *service fee notice (0.1 % per transfer)*, and show “Fund mother wallet” prompt.
    *   _Notes: `start_handler.py -> generate_preview` calls (mocked) API, `message_utils.py -> format_schedule_preview` formats the output including the fee calculated using `SERVICE_FEE_RATE`, and prompts for funding._
*   `[x]` Stream real-time status (TxSent, TxConfirmed, TxFailed) as plain-text messages.
    *   _Notes: `event_system.py` defines events. `start_handler.py -> setup_transaction_event_handlers` subscribes and sends formatted messages (`message_utils.py -> format_transaction_status_message`). Currently relies on simulated events (`event_system.simulate_events_for_run`) as backend logic is missing._

---

## Batch 2: core_essential_logic

**Status:** Undone (Backend Logic)

*   `[ ]` Generate or import mother wallet; deterministically derive ≥ 10 child wallets.
    *   _Notes: Mocked responses in `api_client.py`. Backend `WalletManager` is not implemented._
*   `[ ]` Compute non-overlapping random schedule meeting FR-3 constraints.
    *   _Notes: Mocked schedule generation in `api_client.py`. Backend `Scheduler` is not implemented._
*   `[ ]` Execute transfers with Solana RPC, respecting fee oracle spike threshold, retries, **and deducting a 0.1 % service fee per transfer**.
    *   _Notes: No backend `TxExecutor`, `FeeOracle`, or `FeeCollector` implementation. Fee deduction logic is missing. Event stream is simulated in frontend._

---

## Batch 3: core_important_interface

**Status:** Undone

*   `[ ]` Push CSV summary as document and show “View history” button.
    *   _Notes: No CSV generation/sending code. No "View history" button or related completion logic._
*   `[ ]` Add /history <run_id?> command with paginated inline keyboard of past runs.
    *   _Notes: No `/history` command handler implemented._

---

## Batch 4: core_important_logic

**Status:** Undone (Backend Logic)

*   `[ ]` Persist run metadata, transfers, alerts to Supabase.
    *   _Notes: No `SupabaseGateway` or persistence logic implemented._
*   `[ ]` Generate CSV via pandas, upload to Supabase storage, return URL.
    *   _Notes: No backend `Reporting` service or CSV generation/upload logic._

---

## Batch 5: non_core_important_interface

**Status:** Undone

*   `[ ]` Implement one-time key export flow with “Export keys” button (mother/child).
    *   _Notes: No "Export keys" button or associated frontend flow found._

---

## Batch 6: non_core_important_logic

**Status:** Undone (Backend Logic)

*   `[ ]` Secure key export + memory wipe.
    *   _Notes: No backend `WalletManager` export/wipe functionality implemented._

---

## Batch 7: non_core_optional_interface

**Status:** Undone

*   `[ ]` Localisation scaffolding for UI strings.
    *   _Notes: UI strings in `message_utils.py` and handlers are hardcoded or use f-strings directly, no i18n structure._

---

## Batch 8: non_core_optional_logic

**Status:** Undone (Backend Logic)

*   `[ ]` Configurable thresholds via /settings wizard (gas spike multiplier, retries).
    *   _Notes: No `/settings` command/wizard in frontend. No backend logic for storing/using user settings._

---

**Summary:**

The current codebase focuses heavily on the initial user interaction flow within Telegram (**Batch 1**). It successfully implements the conversation steps, input validation, mock API calls, and basic event handling for status updates (though simulated).

All batches related to **backend logic** (Solana interactions, scheduling algorithms, fee calculation/deduction, persistence, reporting, key management - **Batches 2, 4, 6, 8**) are **undone**, as only the frontend code was provided. The `api_client.py` serves as a placeholder with mocked responses.

Features like history viewing, CSV export, key export (**Batches 3, 5**) and optional enhancements like localisation and settings (**Batches 7, 8**) are also **undone** in both frontend and backend aspects.