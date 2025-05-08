from typing import Dict, List, Any, Optional
from datetime import datetime
from bot.config import SERVICE_FEE_RATE

def format_welcome_message() -> str:
    """
    Format the welcome message shown when a user first starts the bot.
    
    Returns:
        Formatted welcome message text
    """
    return (
        "Welcome to the TokenStorm! 🚀\n\n"
        "This bot helps you generate legitimate-looking trading activity for any SPL token "
        "by creating randomized transfers between multiple wallets.\n\n"
        "Let's get started by setting up a wallet for your transactions."
    )

def format_wallet_created_message(address: str) -> str:
    """
    Format the message shown when a wallet is created.
    
    Args:
        address: The wallet address
        
    Returns:
        Formatted wallet creation message
    """
    return (
        f"✅ Mother wallet created successfully!\n\n"
        f"Address: `{address}`\n\n"
        f"Now, how many child wallets would you like to create? (min: 10)"
    )

def format_wallet_imported_message(address: str) -> str:
    """
    Format the message shown when a wallet is imported.
    
    Args:
        address: The imported wallet address
        
    Returns:
        Formatted wallet import message
    """
    return (
        f"✅ Wallet imported successfully!\n\n"
        f"Address: `{address}`\n\n"
        f"Now, how many child wallets would you like to create? (min: 10)"
    )

def format_child_wallets_message(num_wallets: int, child_addresses: List[str] = None) -> str:
    """
    Format the message confirming the number of child wallets.
    
    Args:
        num_wallets: Number of child wallets
        child_addresses: List of child wallet addresses
        
    Returns:
        Formatted confirmation message
    """
    message = f"✅ {num_wallets} child wallets have been created successfully!\n\n"
    
    # Add child wallet addresses if provided
    if child_addresses:
        message += "Here are your child wallet addresses:\n\n"
        for i, address in enumerate(child_addresses, 1):
            message += f"{i}. `{address}`\n"
        
        message += "\n"
    
    message += (
        f"Now, what's the total token volume in USD you want to generate? "
        f"Enter a number like 1000 for $1,000 USD."
    )
    
    return message

def format_volume_confirmation_message(volume: float) -> str:
    """
    Format the message confirming the volume amount.
    
    Args:
        volume: The volume amount
        
    Returns:
        Formatted volume confirmation message
    """
    return (
        f"✅ Volume amount set to ${volume:,} USD.\n\n"
        f"Now, please enter the token address you want to use:"
    )

def format_schedule_preview(
    schedule: List[Dict[str, Any]], 
    total_volume: float,
    token_address: str,
    num_child_wallets: int
) -> str:
    """
    Format the schedule preview message.
    
    Args:
        schedule: List of transfer operations
        total_volume: The total volume amount
        token_address: The token contract address
        num_child_wallets: Number of child wallets
        
    Returns:
        Formatted schedule preview
    """
    total_fee = total_volume * SERVICE_FEE_RATE
    net_volume = total_volume - total_fee
    
    # Format the message header
    message = (
        f"📋 Transfer Schedule Preview\n\n"
        f"Total volume: {total_volume:,.2f} tokens\n"
        f"Service fee (0.1%): {total_fee:,.2f} tokens\n"
        f"Net transfer volume: {net_volume:,.2f} tokens\n"
        f"Token: {token_address[:6]}...{token_address[-4:]}\n"
        f"Child wallets: {num_child_wallets}\n\n"
        f"Sample transfers (showing first 5):\n\n"
    )
    
    # Add sample transfers (first 5)
    for i, transfer in enumerate(schedule[:5]):
        time_str = datetime.fromtimestamp(transfer["timestamp"]).strftime("%H:%M:%S")
        message += (
            f"{i+1}. {time_str}: {transfer['amount']:,.2f} tokens\n"
            f"   {transfer['from'][:6]}...{transfer['from'][-4:]} → "
            f"{transfer['to'][:6]}...{transfer['to'][-4:]}\n\n"
        )
    
    # Add summary of remaining transfers
    remaining = len(schedule) - 5
    if remaining > 0:
        message += f"...and {remaining} more transfers.\n\n"
    
    message += (
        f"To proceed, please fund the mother wallet with sufficient SOL for gas "
        f"and the required token amount ({total_volume:,.2f} tokens)."
    )
    
    return message

def format_insufficient_balance_message(
    current_balance: float, 
    required_balance: float,
    token_symbol: str = "tokens"
) -> str:
    """
    Format the insufficient balance message.
    
    Args:
        current_balance: Current wallet balance
        required_balance: Required balance to proceed
        token_symbol: Token symbol or name
        
    Returns:
        Formatted insufficient balance message
    """
    return (
        f"⚠️ **Insufficient Balance**\n\n"
        f"Current balance: {current_balance:.3f} {token_symbol}\n"
        f"Required balance: {required_balance:,} {token_symbol}\n\n"
        f"Please fund your wallet with the required amount and then click 'Check Again'."
    )

def format_sufficient_balance_message(
    balance: float,
    token_symbol: str = "tokens"
) -> str:
    """
    Format the sufficient balance message.
    
    Args:
        balance: Current wallet balance
        token_symbol: Token symbol or name
        
    Returns:
        Formatted sufficient balance message
    """
    return (
        f"✅ **Sufficient Balance Detected**\n\n"
        f"Current balance: {balance:.3f} {token_symbol}\n\n"
        f"Ready to begin transfer execution. Click 'Begin Transfers' to start."
    )

def format_transaction_status_message(
    tx_hash: str,
    status: str,
    from_address: str,
    to_address: str,
    amount: float,
    token_symbol: str = "tokens"
) -> str:
    """
    Format transaction status message.
    
    Args:
        tx_hash: Transaction hash
        status: Transaction status
        from_address: Sender address
        to_address: Recipient address
        amount: Transaction amount
        token_symbol: Token symbol or name
        
    Returns:
        Formatted transaction status message
    """
    status_emoji = {
        "sent": "📤",
        "confirmed": "✅",
        "failed": "❌",
        "retrying": "🔄"
    }.get(status.lower(), "ℹ️")
    
    return (
        f"{status_emoji} Transaction {status}\n\n"
        f"Amount: {amount:,.2f} {token_symbol}\n"
        f"From: {from_address[:6]}...{from_address[-4:]}\n"
        f"To: {to_address[:6]}...{to_address[-4:]}\n"
        f"TX: {tx_hash[:8]}...{tx_hash[-6:]}"
    )

def format_error_message(error_message: str) -> str:
    """
    Format an error message for the user.
    
    Args:
        error_message: The error message
        
    Returns:
        Formatted error message
    """
    return f"❌ Error: {error_message}\n\nPlease try again." 