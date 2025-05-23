from typing import Dict, List, Any, Optional
from datetime import datetime

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
        f"Now, what's the total token volume in SOL you want to generate? "
        
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
        f"✅ Volume amount set to {volume:,} SOL.\n\n"
        f"Now, please enter the token contract address where you want to generate the volume"
    )

def format_schedule_preview(
    schedule: List[Dict[str, Any]], 
    total_volume: float,
    token_address: str,
    num_child_wallets: int,
    mother_wallet_address: str
) -> str:
    """
    Format the schedule preview message.
    
    Args:
        schedule: List of transfer operations
        total_volume: The total volume amount
        token_address: The token contract address
        num_child_wallets: Number of child wallets
        mother_wallet_address: The mother wallet address
        
    Returns:
        Formatted schedule preview
    """
    # Simplified message without transfer schedule
    message = (
        f"📋 Overview\n\n"
        f"Total volume to be generated: {total_volume:,.2f} SOL\n"
        f"CA: {token_address[:6]}...{token_address[-4:]}\n\n"
        f"To proceed, please fund the mother wallet:\n`{mother_wallet_address}`\n\n"
        f"Fund it with sufficient SOL for gas "
        f"and the required token amount ({total_volume:,.2f} SOL)."
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
    # Add timestamp to ensure message is different each time
    current_time = datetime.now().strftime("%H:%M:%S")
    
    return (
        f"⚠️ **Insufficient Balance**\n\n"
        f"Current balance: {current_balance:.3f} {token_symbol}\n"
        f"Required balance: {required_balance:,} {token_symbol}\n\n"
        f"Please fund your wallet with the required amount and then click 'Check Again'.\n"
        f"Last checked: {current_time}"
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
    # Add timestamp to ensure message is different each time
    current_time = datetime.now().strftime("%H:%M:%S")
    
    return (
        f"✅ **Sufficient Balance Detected**\n\n"
        f"Current balance: {balance:.3f} {token_symbol}\n\n"
        f"Ready to begin transfer execution. Click 'Begin Transfers' to start.\n"
        f"Last checked: {current_time}"
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

def format_child_balances_overview(child_balances_info: List[Dict[str, Any]]) -> str:
    """
    Format the message displaying child wallet balances and options.

    Args:
        child_balances_info: A list of dicts, each with 'address' and 'balance_sol'.
                            Example: [{'address': 'Addr1...', 'balance_sol': 0.005}, ...]

    Returns:
        Formatted message string.
    """
    if not child_balances_info:
        return "Could not retrieve child wallet balances."

    message_lines = ["📊 **Child Wallet Balances:**\n"]
    total_balance = 0
    
    for i, child_info in enumerate(child_balances_info):
        addr = child_info.get('address', 'N/A')
        bal = child_info.get('balance_sol', 'N/A')
        short_addr = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
        
        if isinstance(bal, (int, float)):
            message_lines.append(f"{i+1}. `{short_addr}`: {bal:.5f} SOL")
            total_balance += bal
        else:
            message_lines.append(f"{i+1}. `{short_addr}`: {bal}")
    
    # Add total if we have numeric balances
    if total_balance > 0:
        message_lines.append(f"\n**Total Balance:** {total_balance:.5f} SOL")

    message_lines.append("\n**What would you like to do next?**")
    return "\n".join(message_lines)

def format_return_funds_summary(results: List[Dict[str, Any]], mother_wallet: str) -> str:
    """
    Format the summary message after attempting to return funds.

    Args:
        results: List of results from each return attempt.
                 Example: [{'child_address': 'Addr1...', 'status': 'success', 'amount_returned_sol': 0.0049}, ...]
        mother_wallet: The address of the mother wallet.

    Returns:
        Formatted summary message.
    """
    if not results:
        return "No fund return operations were attempted."

    mother_short = f"{mother_wallet[:6]}...{mother_wallet[-4:]}"
    message_lines = [f"💸 **Fund Return Summary**\n(to Mother Wallet: `{mother_short}`)\n"]
    success_count = 0
    fail_count = 0
    total_returned = 0

    for res in results:
        child_addr = res.get('child_address', 'N/A')
        child_short = f"{child_addr[:6]}...{child_addr[-4:]}" if len(child_addr) > 10 else child_addr
        status = res.get('status', 'unknown')

        if status == 'success':
            amount = res.get('amount_returned_sol', 0)
            if isinstance(amount, (int, float)):
                message_lines.append(f"✅ From `{child_short}`: {amount:.5f} SOL returned")
                total_returned += amount
            else:
                message_lines.append(f"✅ From `{child_short}`: Returned successfully")
            success_count += 1
        elif status == 'skipped':
            reason = res.get('error', 'Unknown reason')
            message_lines.append(f"⏭️ From `{child_short}`: Skipped - {reason}")
        else:
            error = res.get('error', 'Unknown error')
            message_lines.append(f"❌ From `{child_short}`: Failed - {error}")
            fail_count += 1

    message_lines.append(f"\n**Summary:**")
    message_lines.append(f"✅ Successful: {success_count}")
    if fail_count > 0:
        message_lines.append(f"❌ Failed: {fail_count}")
    if total_returned > 0:
        message_lines.append(f"💰 Total Returned: {total_returned:.5f} SOL")
    
    return "\n".join(message_lines)

def format_child_wallets_funding_status(funding_status: Dict[str, Any]) -> str:
    """
    Format the child wallets funding status check results.

    Args:
        funding_status: Dictionary containing funding status information from check_child_wallets_funding_status

    Returns:
        Formatted funding status message.
    """
    if funding_status.get("error"):
        return f"❌ Error checking funding status: {funding_status['error']}"

    if not funding_status:
        return "❌ No funding status information available."

    all_funded = funding_status.get("all_funded", False)
    total_wallets = funding_status.get("total_wallets", 0)
    funded_wallets = funding_status.get("funded_wallets", 0)
    unfunded_wallets = funding_status.get("unfunded_wallets", 0)
    check_errors = funding_status.get("check_errors", 0)
    required_per_wallet = funding_status.get("required_per_wallet", 0)

    if all_funded:
        return (
            f"✅ **All Child Wallets Sufficiently Funded**\n\n"
            f"📊 Status: {funded_wallets}/{total_wallets} wallets ready\n"
            f"💰 Required: {required_per_wallet:.4f} SOL each\n\n"
            f"Ready to proceed with volume generation!"
        )
    else:
        message_lines = [f"📊 **Child Wallets Funding Status**\n"]
        
        if funded_wallets > 0:
            message_lines.append(f"✅ Funded: {funded_wallets}/{total_wallets} wallets")
        
        if unfunded_wallets > 0:
            message_lines.append(f"❌ Need funding: {unfunded_wallets}/{total_wallets} wallets")
        
        if check_errors > 0:
            message_lines.append(f"⚠️ Check errors: {check_errors}/{total_wallets} wallets")
        
        message_lines.append(f"\n💰 Required per wallet: {required_per_wallet:.4f} SOL")
        
        # Add details for unfunded wallets if available
        unfunded_details = funding_status.get("unfunded_wallet_details", [])
        if unfunded_details and len(unfunded_details) <= 5:  # Show details only for small numbers
            message_lines.append(f"\n**Wallets needing funding:**")
            for wallet_info in unfunded_details[:5]:
                addr = wallet_info.get("address", "N/A")
                balance = wallet_info.get("balance", 0)
                short_addr = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
                message_lines.append(f"• `{short_addr}`: {balance:.4f} SOL")
        
        return "\n".join(message_lines)

def format_return_funds_progress(processed: int, total: int, successful: int, skipped: int, failed: int, current_wallet: Optional[str]) -> str:
    """
    Format the message displaying the progress of returning funds.
    (Placeholder implementation)
    
    Args:
        processed: Number of wallets processed
        total: Total number of wallets
        successful: Number of successful returns
        skipped: Number of skipped returns
        failed: Number of failed returns
        current_wallet: The address of the wallet currently being processed
        
    Returns:
        Formatted progress message string.
    """
    progress_bar_length = 10
    filled_length = int(progress_bar_length * processed // total) if total > 0 else 0
    bar = '█' * filled_length + '-' * (progress_bar_length - filled_length)

    message = (
        f"💸 **Returning Funds to Mother Wallet**\\n\\n"
        f"Progress: [{bar}] {processed}/{total} wallets processed\\n"
        f"✅ Success: {successful} | ⏭️ Skipped: {skipped} | ❌ Failed: {failed}\\n"
    )
    if current_wallet and processed < total:
        message += f"Current: `{current_wallet[:6]}...{current_wallet[-4:]}`"
    elif processed == total:
        message += "All wallets processed."
        
    return message 