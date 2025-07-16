Of course. Here is a granular, step-by-step refactoring plan for `bot/handlers/bundling_handler.py`.

This plan is designed to be executed incrementally. After each step, the bot will remain fully functional, allowing you to test the changes and ensure no regressions have been introduced. This addresses your mandatory requirement for testability throughout the process.

The core strategy is to safely move cohesive blocks of functionality into new, specialized handler files, and then update the main `ConversationHandler` to point to the new locations.

---

### **Phase 1: Extracting Wallet Management Logic**

**Goal:** Move all functions related to creating, funding, and managing wallets into a dedicated `wallet_handler.py`.

*   **Step 1: Create `wallet_handler.py` and Move Airdrop Wallet Logic**
    1.  Create a new file: `bot/handlers/wallet_handler.py`.
    2.  **Move:** Cut the `create_airdrop_wallet` and `handle_airdrop_wallet_choice` functions from `bundling_handler.py` and paste them into `wallet_handler.py`.
    3.  **Update Imports (in `wallet_handler.py`):** Add all necessary imports to the top of `wallet_handler.py` (e.g., `telegram`, `ConversationState`, `session_manager`, `wallet_storage`, etc.).
    4.  **Update `bundling_handler.py`:**
        *   Remove the original function code.
        *   Add the following import: `from .wallet_handler import create_airdrop_wallet, handle_airdrop_wallet_choice`.
        *   Ensure the `ConversationHandler` entries for `CREATE_AIRDROP_WALLET` and `HANDLE_AIRDROP_WALLET_CHOICE` now point to these imported functions.
    5.  **✅ Test Point:** Run the bot. The "Create/Import Airdrop Wallet" part of the workflow should function exactly as before.

*   **Step 2: Move Bundled Wallet Creation Logic**
    1.  **Move:** Cut the `create_bundled_wallets` function from `bundling_handler.py` and paste it into `wallet_handler.py`.
    2.  **Update `bundling_handler.py`:**
        *   Add `create_bundled_wallets` to the import from `.wallet_handler`.
    3.  **✅ Test Point:** Run the bot. The "Create Bundled Wallets" step should function exactly as before.

*   **Step 3: Move Wallet Funding and Balance Check Logic**
    1.  **Move:** Cut the `check_wallet_balance`, `fund_bundled_wallets`, and `return_funds_to_mother` functions from `bundling_handler.py` and paste them into `wallet_handler.py`.
    2.  **Update `bundling_handler.py`:**
        *   Add the moved function names to the import from `.wallet_handler`.
    3.  **✅ Test Point:** Run the bot. The steps for checking the balance, funding the wallets, and returning funds should function exactly as before.

### **Phase 2: Extracting Token Configuration Logic**

**Goal:** Move all functions related to user input for token parameters (name, symbol, image) into a dedicated `token_config_handler.py`.

*   **Step 4: Create `token_config_handler.py` and Move Parameter Input Logic**
    1.  Create a new file: `bot/handlers/token_config_handler.py`.
    2.  **Move:** Cut the `token_parameter_input` and all related `handle_..._input` functions (e.g., `handle_token_name_input`, `handle_token_symbol_input`, etc.) from `bundling_handler.py` and paste them into `token_config_handler.py`.
    3.  **Update Imports (in `token_config_handler.py`):** Add all necessary imports.
    4.  **Update `bundling_handler.py`:**
        *   Import the moved functions from `.token_config_handler`.
    5.  **✅ Test Point:** Run the bot. The entire multi-step process of entering the token's name, symbol, description, and website should function exactly as before.

*   **Step 5: Move Token Image Handling Logic**
    1.  **Move:** Cut the `handle_token_image` and `handle_no_token_image` functions from `bundling_handler.py` and paste them into `token_config_handler.py`.
    2.  **Update `bundling_handler.py`:**
        *   Add the moved function names to the import from `.token_config_handler`.
    3.  **✅ Test Point:** Run the bot. The step for uploading a token image or skipping it should function exactly as before.

### **Phase 3: Extracting Final Token Creation Logic**

**Goal:** Move the final confirmation and creation logic into a dedicated `token_creation_handler.py`.

*   **Step 6: Create `token_creation_handler.py` and Move Finalization Logic**
    1.  Create a new file: `bot/handlers/token_creation_handler.py`.
    2.  **Move:** Cut the `preview_token_creation` and `create_token_final` functions from `bundling_handler.py` and paste them into `token_creation_handler.py`.
    3.  **Update Imports (in `token_creation_handler.py`):** Add all necessary imports.
    4.  **Update `bundling_handler.py`:**
        *   Import the moved functions from `.token_creation_handler`.
    5.  **✅ Test Point:** Run the bot. The final preview screen and the "Create Token" button press should function exactly as before.

### **Phase 4: Final Cleanup and Documentation**

**Goal:** Clean up the main `bundling_handler.py` to be a pure orchestrator and update documentation to reflect the new, more modular architecture.

*   **Step 7: Refactor `bundling_handler.py` as an Orchestrator**
    1.  Review `bundling_handler.py`. It should now contain almost no business logic. Its primary role is to import the handlers from the other files and assemble them into the `ConversationHandler`.
    2.  Clean up the import statements, grouping them by the new handler modules.
    3.  Ensure the `bundling_conversation_handler` variable is clearly defined and is the only major export from this file.
    4.  **✅ Test Point:** Perform a full, end-to-end test of the entire token bundling workflow to ensure all parts are still correctly wired together.

*   **Step 8: Update Architecture Documentation**
    1.  Open `bundling_handler_architecture.md`.
    2.  Update the "Component Relationship Map" (the Mermaid diagram) to show that `bundling_handler.py` now orchestrates the new handlers (`wallet_handler`, `token_config_handler`, `token_creation_handler`).
    3.  Update the text descriptions to reflect this new, more modular flow.

After completing these steps, your refactoring will be complete. The functionality will be unchanged, but the code will be significantly more organized, maintainable, and easier to understand.