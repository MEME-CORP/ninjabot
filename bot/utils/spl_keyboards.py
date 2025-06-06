"""
SPL Token Trading Keyboard Utilities for Telegram Bot.
Provides inline keyboards for SPL trading configuration and navigation.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict, Any

# Import CallbackPrefix values directly to avoid circular import
class CallbackPrefix:
    SPL_OPERATION = "spl_op_"
    SPL_TOKEN_PAIR = "spl_pair_"
    SPL_AMOUNT_STRATEGY = "spl_amt_"
    SPL_EXECUTION_MODE = "spl_exec_"
    SPL_CONFIRM = "spl_confirm_"


def create_spl_operation_keyboard() -> InlineKeyboardMarkup:
    """
    Create keyboard for SPL operation selection (Buy/Sell).
    
    Returns:
        InlineKeyboardMarkup for operation selection
    """
    keyboard = [
        [
            InlineKeyboardButton("💰 Buy", callback_data=f"{CallbackPrefix.SPL_OPERATION}buy"),
            InlineKeyboardButton("💸 Sell", callback_data=f"{CallbackPrefix.SPL_OPERATION}sell")
        ],
        [
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_token_pair_quick_selection_keyboard() -> InlineKeyboardMarkup:
    """
    Create keyboard for quick token pair selection.
    
    Returns:
        InlineKeyboardMarkup for quick token pair selection
    """
    keyboard = [
        [
            InlineKeyboardButton("SOL → USDC", callback_data=f"{CallbackPrefix.SPL_TOKEN_PAIR}SOL_USDC"),
            InlineKeyboardButton("SOL → USDT", callback_data=f"{CallbackPrefix.SPL_TOKEN_PAIR}SOL_USDT")
        ],
        [
            InlineKeyboardButton("USDC → SOL", callback_data=f"{CallbackPrefix.SPL_TOKEN_PAIR}USDC_SOL"),
            InlineKeyboardButton("USDT → SOL", callback_data=f"{CallbackPrefix.SPL_TOKEN_PAIR}USDT_SOL")
        ],
        [
            InlineKeyboardButton("SOL → BONK", callback_data=f"{CallbackPrefix.SPL_TOKEN_PAIR}SOL_BONK"),
            InlineKeyboardButton("BONK → SOL", callback_data=f"{CallbackPrefix.SPL_TOKEN_PAIR}BONK_SOL")
        ],
        [
            InlineKeyboardButton("✏️ Custom Pair", callback_data=f"{CallbackPrefix.SPL_TOKEN_PAIR}custom"),
            InlineKeyboardButton("🔙 Back", callback_data="spl_back_operation")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_amount_strategy_keyboard() -> InlineKeyboardMarkup:
    """
    Create keyboard for amount strategy selection.
    
    Returns:
        InlineKeyboardMarkup for amount strategy selection
    """
    keyboard = [
        [
            InlineKeyboardButton("🔒 Fixed Amount", callback_data=f"{CallbackPrefix.SPL_AMOUNT_STRATEGY}fixed"),
            InlineKeyboardButton("📊 Percentage", callback_data=f"{CallbackPrefix.SPL_AMOUNT_STRATEGY}percentage")
        ],
        [
            InlineKeyboardButton("🎲 Random Range", callback_data=f"{CallbackPrefix.SPL_AMOUNT_STRATEGY}random"),
            InlineKeyboardButton("✏️ Custom Amounts", callback_data=f"{CallbackPrefix.SPL_AMOUNT_STRATEGY}custom")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="spl_back_token_pair")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_execution_mode_keyboard() -> InlineKeyboardMarkup:
    """
    Create keyboard for execution mode selection.
    
    Returns:
        InlineKeyboardMarkup for execution mode selection
    """
    keyboard = [
        [
            InlineKeyboardButton("📋 Sequential", callback_data=f"{CallbackPrefix.SPL_EXECUTION_MODE}sequential"),
            InlineKeyboardButton("⚡ Parallel", callback_data=f"{CallbackPrefix.SPL_EXECUTION_MODE}parallel")
        ],
        [
            InlineKeyboardButton("📦 Batch", callback_data=f"{CallbackPrefix.SPL_EXECUTION_MODE}batch"),
            InlineKeyboardButton("🔙 Back", callback_data="spl_back_amount_strategy")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_spl_preview_keyboard(dry_run: bool = True) -> InlineKeyboardMarkup:
    """
    Create keyboard for SPL operation preview confirmation.
    
    Args:
        dry_run: Whether this is a dry run or live operation
        
    Returns:
        InlineKeyboardMarkup for preview confirmation
    """
    if dry_run:
        keyboard = [
            [
                InlineKeyboardButton("🧪 Start Dry Run", callback_data=f"{CallbackPrefix.SPL_CONFIRM}dry_run"),
                InlineKeyboardButton("🚀 Go Live", callback_data=f"{CallbackPrefix.SPL_CONFIRM}live")
            ],
            [
                InlineKeyboardButton("✏️ Edit Configuration", callback_data="spl_edit_config"),
                InlineKeyboardButton("🔙 Back", callback_data="spl_back_execution_mode")
            ]
        ]
    else:
        keyboard = [
            [
                InlineKeyboardButton("🚀 Execute Operation", callback_data=f"{CallbackPrefix.SPL_CONFIRM}execute"),
                InlineKeyboardButton("🧪 Switch to Dry Run", callback_data=f"{CallbackPrefix.SPL_CONFIRM}dry_run")
            ],
            [
                InlineKeyboardButton("✏️ Edit Configuration", callback_data="spl_edit_config"),
                InlineKeyboardButton("🔙 Back", callback_data="spl_back_execution_mode")
            ]
        ]
    
    return InlineKeyboardMarkup(keyboard)


def create_spl_execution_control_keyboard(operation_id: str) -> InlineKeyboardMarkup:
    """
    Create keyboard for controlling SPL operation execution.
    
    Args:
        operation_id: ID of the running operation
        
    Returns:
        InlineKeyboardMarkup for execution control
    """
    keyboard = [
        [
            InlineKeyboardButton("🔄 Refresh Status", callback_data=f"spl_refresh_{operation_id}"),
            InlineKeyboardButton("🛑 Cancel Operation", callback_data=f"spl_cancel_{operation_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_spl_results_keyboard(has_failed: bool = False) -> InlineKeyboardMarkup:
    """
    Create keyboard for SPL operation results.
    
    Args:
        has_failed: Whether some operations failed
        
    Returns:
        InlineKeyboardMarkup for results actions
    """
    keyboard = []
    
    if has_failed:
        keyboard.append([
            InlineKeyboardButton("🔁 Retry Failed", callback_data="spl_retry_failed"),
            InlineKeyboardButton("📊 View Report", callback_data="spl_view_report")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("📊 View Report", callback_data="spl_view_report")
        ])
    
    keyboard.extend([
        [
            InlineKeyboardButton("🔄 New Operation", callback_data="spl_new_operation"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main")
        ]
    ])
    
    return InlineKeyboardMarkup(keyboard)


def create_token_selection_keyboard(popular_tokens: List[str] = None) -> InlineKeyboardMarkup:
    """
    Create keyboard for token selection with popular tokens.
    
    Args:
        popular_tokens: List of popular token symbols
        
    Returns:
        InlineKeyboardMarkup for token selection
    """
    if not popular_tokens:
        popular_tokens = ["SOL", "USDC", "USDT", "BONK", "RAY", "ORCA"]
    
    keyboard = []
    
    # Add popular tokens in rows of 3
    for i in range(0, len(popular_tokens), 3):
        row = []
        for token in popular_tokens[i:i+3]:
            row.append(InlineKeyboardButton(token, callback_data=f"select_token_{token}"))
        keyboard.append(row)
    
    # Add custom token option
    keyboard.append([
        InlineKeyboardButton("✏️ Custom Token/Mint", callback_data="select_token_custom"),
        InlineKeyboardButton("🔙 Back", callback_data="spl_back")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def create_fixed_amount_keyboard() -> InlineKeyboardMarkup:
    """
    Create keyboard for fixed amount quick selection.
    
    Returns:
        InlineKeyboardMarkup for fixed amount selection
    """
    amounts = ["0.01", "0.05", "0.1", "0.25", "0.5", "1.0"]
    
    keyboard = []
    
    # Add amounts in rows of 3
    for i in range(0, len(amounts), 3):
        row = []
        for amount in amounts[i:i+3]:
            row.append(InlineKeyboardButton(f"{amount} SOL", callback_data=f"fixed_amount_{amount}"))
        keyboard.append(row)
    
    # Add custom amount option
    keyboard.append([
        InlineKeyboardButton("✏️ Custom Amount", callback_data="fixed_amount_custom"),
        InlineKeyboardButton("🔙 Back", callback_data="spl_back_amount_strategy")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def create_percentage_keyboard() -> InlineKeyboardMarkup:
    """
    Create keyboard for percentage quick selection.
    
    Returns:
        InlineKeyboardMarkup for percentage selection
    """
    percentages = ["10%", "25%", "50%", "75%", "90%", "100%"]
    
    keyboard = []
    
    # Add percentages in rows of 3
    for i in range(0, len(percentages), 3):
        row = []
        for percentage in percentages[i:i+3]:
            percentage_value = percentage.rstrip('%')
            row.append(InlineKeyboardButton(percentage, callback_data=f"percentage_{percentage_value}"))
        keyboard.append(row)
    
    # Add custom percentage option
    keyboard.append([
        InlineKeyboardButton("✏️ Custom Percentage", callback_data="percentage_custom"),
        InlineKeyboardButton("🔙 Back", callback_data="spl_back_amount_strategy")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def create_slippage_keyboard() -> InlineKeyboardMarkup:
    """
    Create keyboard for slippage tolerance selection.
    
    Returns:
        InlineKeyboardMarkup for slippage selection
    """
    slippages = ["0.1%", "0.5%", "1.0%", "2.0%", "3.0%", "5.0%"]
    
    keyboard = []
    
    # Add slippages in rows of 3
    for i in range(0, len(slippages), 3):
        row = []
        for slippage in slippages[i:i+3]:
            slippage_bps = int(float(slippage.rstrip('%')) * 100)
            row.append(InlineKeyboardButton(slippage, callback_data=f"slippage_{slippage_bps}"))
        keyboard.append(row)
    
    # Add custom slippage option
    keyboard.append([
        InlineKeyboardButton("✏️ Custom Slippage", callback_data="slippage_custom"),
        InlineKeyboardButton("🔙 Back", callback_data="spl_back")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def create_parallel_config_keyboard() -> InlineKeyboardMarkup:
    """
    Create keyboard for parallel execution configuration.
    
    Returns:
        InlineKeyboardMarkup for parallel config
    """
    concurrent_options = ["3", "5", "10", "15", "20"]
    
    keyboard = []
    
    # Add concurrent options in rows
    for i in range(0, len(concurrent_options), 3):
        row = []
        for option in concurrent_options[i:i+3]:
            row.append(InlineKeyboardButton(f"{option} concurrent", callback_data=f"parallel_concurrent_{option}"))
        keyboard.append(row)
    
    # Add custom and back options
    keyboard.append([
        InlineKeyboardButton("✏️ Custom", callback_data="parallel_concurrent_custom"),
        InlineKeyboardButton("🔙 Back", callback_data="spl_back_execution_mode")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def create_batch_config_keyboard() -> InlineKeyboardMarkup:
    """
    Create keyboard for batch execution configuration.
    
    Returns:
        InlineKeyboardMarkup for batch config
    """
    batch_sizes = ["5", "10", "15", "20", "25"]
    
    keyboard = []
    
    # Add batch sizes in rows
    for i in range(0, len(batch_sizes), 3):
        row = []
        for size in batch_sizes[i:i+3]:
            row.append(InlineKeyboardButton(f"Batch of {size}", callback_data=f"batch_size_{size}"))
        keyboard.append(row)
    
    # Add custom and back options
    keyboard.append([
        InlineKeyboardButton("✏️ Custom Size", callback_data="batch_size_custom"),
        InlineKeyboardButton("🔙 Back", callback_data="spl_back_execution_mode")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def create_confirmation_keyboard(action: str, item_id: str = "") -> InlineKeyboardMarkup:
    """
    Create a generic confirmation keyboard.
    
    Args:
        action: The action to confirm
        item_id: Optional item identifier
        
    Returns:
        InlineKeyboardMarkup for confirmation
    """
    confirm_data = f"confirm_{action}_{item_id}" if item_id else f"confirm_{action}"
    cancel_data = f"cancel_{action}_{item_id}" if item_id else f"cancel_{action}"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=confirm_data),
            InlineKeyboardButton("❌ Cancel", callback_data=cancel_data)
        ]
    ]
    return InlineKeyboardMarkup(keyboard) 