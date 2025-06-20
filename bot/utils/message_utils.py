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

def format_existing_child_wallets_found_message(wallet_address: str, num_existing: int) -> str:
    """
    Format message when existing child wallets are found for a mother wallet.
    
    Args:
        wallet_address: The mother wallet address
        num_existing: Number of existing child wallets
        
    Returns:
        Formatted message for existing child wallets
    """
    return (
        f"✅ Using saved wallet: `{wallet_address}`\n\n"
        f"Found {num_existing} existing child wallets associated with this mother wallet.\n\n"
        f"You can use these existing wallets or create a new set (this will replace the existing ones)."
    )

def format_no_child_wallets_found_message(wallet_address: str) -> str:
    """
    Format message when no child wallets are found for a mother wallet.
    
    Args:
        wallet_address: The mother wallet address
        
    Returns:
        Formatted message for no existing child wallets
    """
    return (
        f"✅ Using saved wallet: `{wallet_address}`\n\n"
        f"No child wallets found for this mother wallet.\n\n"
        f"How many child wallets would you like to create? (min: 10)"
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
    Format the message confirming the volume amount for SPL token volume generation.
    
    Args:
        volume: The volume amount
        
    Returns:
        Formatted volume confirmation message
    """
    return (
        f"✅ Volume amount set to {volume:,} SOL.\n\n"
        f"This volume will be generated through transfers between your child wallets for the SPL token you specify.\n\n"
        f"⚡ **Volume Enforcement**: The system will strictly enforce this total limit - "
        f"no individual swap will exceed the remaining volume budget to ensure compliance."
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

# SPL Token Trading Message Formatters

def format_spl_operation_choice() -> str:
    """
    Format the SPL operation choice message.
    
    Returns:
        Formatted operation choice message
    """
    return (
        "🔄 **SPL Token Trading**\n\n"
        "Choose the type of operation you want to perform:\n\n"
        "**Buy**: Exchange SOL or other tokens for a target token\n"
        "**Sell**: Exchange a token for SOL or other tokens\n\n"
        "Both operations will be executed across your child wallets."
    )

def format_token_pair_selection(operation: str) -> str:
    """
    Format token pair selection message.
    
    Args:
        operation: "buy" or "sell"
        
    Returns:
        Formatted token pair selection message
    """
    if operation.lower() == "buy":
        return (
            "💰 **Token Pair Configuration - Buy Operation**\n\n"
            "You need to specify what tokens you want to exchange:\n\n"
            "**Input Token**: The token you want to spend (e.g., SOL, USDC)\n"
            "**Output Token**: The token you want to receive\n\n"
            "Please enter the token pair in this format:\n"
            "`INPUT_TOKEN -> OUTPUT_TOKEN`\n\n"
            "Examples:\n"
            "• `SOL -> USDC` (Buy USDC with SOL)\n"
            "• `USDC -> BONK` (Buy BONK with USDC)\n"
            "• `SOL -> EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` (Using mint address)"
        )
    else:
        return (
            "💸 **Token Pair Configuration - Sell Operation**\n\n"
            "You need to specify what tokens you want to exchange:\n\n"
            "**Input Token**: The token you want to sell\n"
            "**Output Token**: The token you want to receive (e.g., SOL, USDC)\n\n"
            "Please enter the token pair in this format:\n"
            "`INPUT_TOKEN -> OUTPUT_TOKEN`\n\n"
            "Examples:\n"
            "• `BONK -> SOL` (Sell BONK for SOL)\n"
            "• `USDC -> SOL` (Sell USDC for SOL)\n"
            "• `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v -> SOL` (Using mint address)"
        )

def format_amount_strategy_explanation() -> str:
    """
    Format amount strategy explanation message.
    
    Returns:
        Formatted strategy explanation
    """
    return (
        "📊 **Amount Strategy Selection**\n\n"
        "Choose how amounts will be calculated for each wallet:\n\n"
        "**Fixed Amount**: Same amount for all wallets\n"
        "• Example: 0.1 SOL per wallet\n\n"
        "**Percentage**: Percentage of each wallet's balance\n"
        "• Example: 50% of each wallet's token balance\n\n"
        "**Random Range**: Random amount within specified range\n"
        "• Example: Random between 0.05-0.25 SOL\n\n"
        "**Custom Amounts**: Specify exact amount for each wallet\n"
        "• Example: Different amounts per wallet"
    )

def format_spl_operation_preview(config_summary: Dict[str, Any]) -> str:
    """
    Format SPL operation preview message.
    
    Args:
        config_summary: Configuration summary dictionary
        
    Returns:
        Formatted preview message
    """
    operation = config_summary.get('operation', 'Unknown').upper()
    input_token = config_summary.get('input_token', 'Unknown')
    output_token = config_summary.get('output_token', 'Unknown')
    strategy = config_summary.get('amount_strategy', 'Unknown')
    execution_mode = config_summary.get('execution_mode', 'Sequential')
    wallet_count = config_summary.get('wallet_count', 0)
    estimated_total = config_summary.get('estimated_total_input', 0)
    
    # Operation emoji
    op_emoji = "💰" if operation == "BUY" else "💸"
    
    message = f"{op_emoji} **{operation} Operation Preview**\n\n"
    
    # Token pair
    message += f"**Token Pair**: {input_token} → {output_token}\n"
    
    # Amount strategy details
    if strategy == "FIXED":
        base_amount = config_summary.get('base_amount', 0)
        message += f"**Amount**: {base_amount} {input_token} per wallet\n"
    elif strategy == "PERCENTAGE":
        percentage = config_summary.get('percentage', 0) * 100
        message += f"**Amount**: {percentage}% of wallet balance\n"
    elif strategy == "RANDOM":
        min_amount = config_summary.get('min_amount', 0)
        max_amount = config_summary.get('max_amount', 0)
        message += f"**Amount**: {min_amount} - {max_amount} {input_token} per wallet\n"
    
    # Execution details
    message += f"**Execution**: {execution_mode.title()}\n"
    message += f"**Wallets**: {wallet_count}\n"
    
    if estimated_total > 0:
        message += f"**Est. Total Input**: {estimated_total:.4f} {input_token}\n"
    
    # Additional settings
    slippage = config_summary.get('slippage_bps', 50) / 100
    message += f"**Slippage**: {slippage}%\n"
    
    dry_run = config_summary.get('dry_run', True)
    if dry_run:
        message += "\n⚠️ **Dry Run Mode**: No actual transactions will be executed\n"
    
    message += "\nProceed with this configuration?"
    
    return message

def format_spl_execution_progress(progress_data: Dict[str, Any]) -> str:
    """
    Format SPL execution progress message.
    
    Args:
        progress_data: Progress information dictionary
        
    Returns:
        Formatted progress message
    """
    operation = progress_data.get('operation', 'Unknown').upper()
    processed = progress_data.get('processed', 0)
    total = progress_data.get('total', 0)
    successful = progress_data.get('successful', 0)
    failed = progress_data.get('failed', 0)
    current_wallet = progress_data.get('current_wallet')
    
    # Progress calculation
    progress_percentage = int((processed / total) * 100) if total > 0 else 0
    
    # Visual progress bar
    bar_length = 10
    filled_length = int(bar_length * progress_percentage / 100)
    progress_bar = "█" * filled_length + "░" * (bar_length - filled_length)
    
    # Operation emoji
    op_emoji = "💰" if operation == "BUY" else "💸"
    
    message = f"{op_emoji} **{operation} Operation Progress**\n\n"
    message += f"Progress: {progress_percentage}% [{progress_bar}]\n"
    message += f"Processed: {processed}/{total} wallets\n\n"
    
    message += f"✅ Successful: {successful}\n"
    message += f"❌ Failed: {failed}\n"
    
    if current_wallet:
        message += f"\n🔄 Current: `{current_wallet[:8]}...{current_wallet[-6:]}`"
    
    return message

def format_spl_results_summary(results_data: Dict[str, Any]) -> str:
    """
    Format SPL operation results summary.
    
    Args:
        results_data: Results information dictionary
        
    Returns:
        Formatted results summary
    """
    operation = results_data.get('operation', 'Unknown').upper()
    total_wallets = results_data.get('total_wallets', 0)
    successful = results_data.get('successful_swaps', 0)
    failed = results_data.get('failed_swaps', 0)
    total_input = results_data.get('total_input_amount', 0)
    total_output = results_data.get('total_output_amount', 0)
    input_token = results_data.get('input_token', 'Unknown')
    output_token = results_data.get('output_token', 'Unknown')
    execution_time = results_data.get('execution_time_seconds', 0)
    
    # Operation emoji
    op_emoji = "💰" if operation == "BUY" else "💸"
    status_emoji = "✅" if failed == 0 else "⚠️"
    
    message = f"{status_emoji} **{operation} Operation Complete**\n\n"
    
    # Success rate
    success_rate = (successful / total_wallets * 100) if total_wallets > 0 else 0
    message += f"**Success Rate**: {success_rate:.1f}% ({successful}/{total_wallets})\n"
    
    # Amounts
    if total_input > 0:
        message += f"**Total {input_token} Used**: {total_input:.6f}\n"
    if total_output > 0:
        message += f"**Total {output_token} Received**: {total_output:.6f}\n"
    
    # Timing
    if execution_time > 0:
        message += f"**Execution Time**: {execution_time:.1f}s\n"
    
    # Status breakdown
    message += f"\n📊 **Breakdown**:\n"
    message += f"✅ Successful: {successful}\n"
    message += f"❌ Failed: {failed}\n"
    
    if failed > 0:
        message += f"\n⚠️ Some swaps failed. Check the detailed report for more information."
    
    return message

def format_spl_error_message(error_type: str, error_details: str) -> str:
    """
    Format SPL operation error message.
    
    Args:
        error_type: Type of error
        error_details: Detailed error information
        
    Returns:
        Formatted error message
    """
    error_emojis = {
        'validation': '⚠️',
        'balance': '💰',
        'network': '🌐',
        'configuration': '⚙️',
        'unknown': '❌'
    }
    
    emoji = error_emojis.get(error_type, '❌')
    
    message = f"{emoji} **SPL Operation Error**\n\n"
    message += f"**Error Type**: {error_type.title()}\n"
    message += f"**Details**: {error_details}\n\n"
    
    # Add helpful suggestions based on error type
    if error_type == 'balance':
        message += "💡 **Suggestion**: Ensure wallets have sufficient balance for the operation."
    elif error_type == 'network':
        message += "💡 **Suggestion**: Check your internet connection and try again."
    elif error_type == 'validation':
        message += "💡 **Suggestion**: Review your configuration and ensure all values are correct."
    else:
        message += "💡 **Suggestion**: Please try again or contact support if the issue persists."
    
    return message

def format_spl_token_validation_message(token_address: str, is_valid: bool, token_info: Dict[str, Any] = None) -> str:
    """
    Format SPL token validation confirmation message.
    
    Args:
        token_address: The SPL token contract address
        is_valid: Whether the token is valid
        token_info: Optional token information
        
    Returns:
        Formatted validation message
    """
    if not is_valid:
        return format_error_message(
            f"Invalid SPL token contract address: {token_address}\n\n"
            "Please ensure you're using a valid Solana token mint address."
        )
    
    message = f"✅ **SPL Token Verified**\n\n"
    message += f"**Contract Address**: `{token_address}`\n"
    
    if token_info:
        if token_info.get('symbol'):
            message += f"**Symbol**: {token_info['symbol']}\n"
        if token_info.get('name'):
            message += f"**Name**: {token_info['name']}\n"
        if token_info.get('decimals') is not None:
            message += f"**Decimals**: {token_info['decimals']}\n"
    
    message += f"\n🔄 Ready to generate volume for this SPL token!"
    
    return message

def format_volume_generation_insufficient_balance_message(
    total_wallets: int,
    wallets_with_insufficient_balance: int,
    required_per_wallet: float,
    reserved_per_wallet: float,
    min_swap_amount: float
) -> str:
    """
    Format message for insufficient balance during volume generation.
    
    Args:
        total_wallets: Total number of child wallets
        wallets_with_insufficient_balance: Number of wallets with insufficient balance
        required_per_wallet: Total SOL required per wallet
        reserved_per_wallet: SOL reserved for rent/fees per wallet
        min_swap_amount: Minimum SOL amount needed for swaps
        
    Returns:
        Formatted insufficient balance message
    """
    
    message = f"⚠️ **Insufficient Balance for Volume Generation**\n\n"
    
    message += f"**Status**: {wallets_with_insufficient_balance} out of {total_wallets} child wallets have insufficient balance for SPL swaps.\n\n"
    
    message += f"**Balance Requirements per Wallet**:\n"
    message += f"• **Total Required**: {required_per_wallet:.6f} SOL\n"
    message += f"• **Reserved for Rent/Fees**: {reserved_per_wallet:.6f} SOL\n"
    message += f"• **Available for Swaps**: {min_swap_amount:.6f} SOL\n\n"
    
    message += f"**What this means**:\n"
    message += f"• Each wallet needs at least {required_per_wallet:.6f} SOL to perform volume generation\n"
    message += f"• {reserved_per_wallet:.6f} SOL is reserved for account rent and transaction fees\n"
    message += f"• The remaining {min_swap_amount:.6f} SOL is used for token swaps\n\n"
    
    message += f"**Solutions**:\n"
    message += f"• **Fund child wallets** with more SOL (recommended)\n"
    message += f"• **Reduce volume amount** to match available balance\n"
    message += f"• **Check wallet balances** to ensure funding was successful\n\n"
    
    message += f"💡 **Tip**: Use 'Fund Child Wallets' option to add more SOL to your child wallets."
    
    return message

def format_sell_remaining_balance_summary(sell_results: Dict[str, Any], token_address: str) -> str:
    """
    Format a summary message for sell remaining balance operation.
    
    Args:
        sell_results: Results from the sell operation
        token_address: Token contract address
        
    Returns:
        Formatted message string
    """
    status_emoji = {
        "success": "✅",
        "partial_success": "⚠️",
        "failed": "❌",
        "no_operations": "ℹ️"
    }.get(sell_results.get("status", "failed"), "ℹ️")
    
    # Format token address display
    token_display = f"{token_address[:8]}...{token_address[-8:]}" if len(token_address) > 16 else token_address
    
    message = (
        f"{status_emoji} **Token Sale Complete**\n\n"
        f"**Token:** `{token_display}`\n"
        f"**Status:** {sell_results.get('status', 'Unknown').replace('_', ' ').title()}\n"
        f"**Batch ID:** `{sell_results.get('batch_id', 'N/A')}`\n\n"
        f"📊 **Sale Summary:**\n"
        f"  - Total Wallets: {sell_results.get('total_wallets', 0)}\n"
        f"  - Sales Attempted: {sell_results.get('sells_attempted', 0)}\n"
        f"  - Sales Successful: {sell_results.get('sells_succeeded', 0)}\n"
        f"  - Sales Failed: {sell_results.get('sells_failed', 0)}\n"
        f"  - Sales Skipped: {sell_results.get('sells_skipped', 0)}\n"
        f"  - Total SOL Received: {sell_results.get('total_sol_received', 0):.6f} SOL\n"
    )
    
    # Add performance metrics if available
    total_attempted = sell_results.get('sells_attempted', 0)
    if total_attempted > 0:
        success_rate = (sell_results.get('sells_succeeded', 0) / total_attempted) * 100
        message += f"  - Success Rate: {success_rate:.1f}%\n"
    
    # Add helpful notes based on results
    if sell_results.get('sells_skipped', 0) > 0:
        message += f"\n💡 **Note:** {sell_results.get('sells_skipped', 0)} wallet(s) were skipped due to insufficient token balance."
    
    if sell_results.get('sells_failed', 0) > 0:
        message += f"\n⚠️ **Warning:** {sell_results.get('sells_failed', 0)} sale(s) failed. Check individual wallet results for details."
    
    return message

# =============================================================================
# PUMPFUN BUNDLING MESSAGE FORMATTERS
# =============================================================================

def format_activity_selection_message() -> str:
    """
    Format activity selection message for choosing between Volume Generation and Bundling.
    
    Returns:
        Formatted activity selection message
    """
    message = "🚀 **Welcome to NinjaBot Trading Platform!**\n\n"
    message += "Please select your trading activity:\n\n"
    message += "📊 **Volume Generation**\n"
    message += "Generate trading volume for existing SPL tokens using Jupiter aggregator.\n"
    message += "• Trade SOL ↔ SPL tokens\n"
    message += "• Configurable volume targets\n"
    message += "• Multiple wallet coordination\n\n"
    message += "🚀 **Token Bundling (PumpFun)**\n"
    message += "Create new tokens and execute coordinated buy/sell operations.\n"
    message += "• Create custom tokens\n"
    message += "• Batch wallet operations\n"
    message += "• Bundle transactions via Jito\n\n"
    message += "Choose your preferred activity to continue:"
    
    return message

def format_activity_confirmation_message(activity_type: str) -> str:
    """
    Format activity confirmation message.
    
    Args:
        activity_type: Selected activity ('volume_generation' or 'bundling')
        
    Returns:
        Formatted confirmation message
    """
    if activity_type == "volume_generation":
        message = "📊 **Volume Generation Selected**\n\n"
        message += "You've chosen to generate trading volume for existing SPL tokens.\n"
        message += "This will help increase trading activity and market presence.\n\n"
        message += "Let's start by setting up your wallet configuration..."
    else:
        message = "🚀 **Token Bundling Selected**\n\n"
        message += "You've chosen to create and bundle new tokens using PumpFun.\n"
        message += "This includes token creation and coordinated trading operations.\n\n"
        message += "Let's start by setting up your wallet infrastructure..."
    
    return message

def format_token_creation_start_message() -> str:
    """
    Format token creation start message.
    
    Returns:
        Formatted token creation start message
    """
    message = "🪙 **Token Creation Setup**\n\n"
    message += "Let's create your custom token! I'll guide you through each parameter:\n\n"
    message += "📝 **Required Information:**\n"
    message += "• Token Name (e.g., 'My Amazing Token')\n"
    message += "• Token Symbol (e.g., 'MAT')\n"
    message += "• Description\n"
    message += "• Token Image\n\n"
    message += "🔗 **Optional Social Links:**\n"
    message += "• Twitter URL\n"
    message += "• Telegram URL\n"
    message += "• Website URL\n\n"
    message += "Let's start with the token name..."
    
    return message

def format_token_parameter_request(parameter_name: str, description: str, optional: bool = False) -> str:
    """
    Format token parameter request message.
    
    Args:
        parameter_name: Name of the parameter being requested
        description: Description of the parameter
        optional: Whether the parameter is optional
        
    Returns:
        Formatted parameter request message
    """
    required_text = "Optional" if optional else "Required"
    
    message = f"📝 **{parameter_name}** ({'Optional' if optional else 'Required'})\n\n"
    message += f"{description}\n\n"
    
    if parameter_name.lower() == "name":
        message += "💡 **Guidelines:**\n"
        message += "• Maximum 32 characters\n"
        message += "• Use a memorable, unique name\n"
        message += "• Avoid special characters\n\n"
    elif parameter_name.lower() == "symbol":
        message += "💡 **Guidelines:**\n"
        message += "• Maximum 10 characters\n"
        message += "• Only letters and numbers\n"
        message += "• Usually 3-4 characters (e.g., BTC, ETH)\n\n"
    elif parameter_name.lower() == "description":
        message += "💡 **Guidelines:**\n"
        message += "• Maximum 500 characters\n"
        message += "• Explain your token's purpose\n"
        message += "• Include key features or use cases\n\n"
    
    message += f"Please enter your token {parameter_name.lower()}:"
    
    return message

def format_token_creation_preview(token_params: Dict[str, Any]) -> str:
    """
    Format token creation preview message.
    
    Args:
        token_params: Dictionary containing token parameters
        
    Returns:
        Formatted preview message
    """
    message = "🔍 **Token Creation Preview**\n\n"
    message += "📝 **Token Details:**\n"
    message += f"• **Name:** {token_params.get('name', 'N/A')}\n"
    message += f"• **Symbol:** {token_params.get('symbol', 'N/A')}\n"
    message += f"• **Description:** {token_params.get('description', 'N/A')}\n"
    initial_supply = token_params.get('initial_supply', '1000000000')
    try:
        # Try to format as number with commas
        supply_num = int(initial_supply) if isinstance(initial_supply, str) else initial_supply
        message += f"• **Initial Supply:** {supply_num:,}\n\n"
    except (ValueError, TypeError):
        # Fallback to string representation
        message += f"• **Initial Supply:** {initial_supply}\n\n"
    
    message += "🔗 **Social Links:**\n"
    twitter = token_params.get('twitter', '')
    telegram = token_params.get('telegram', '')
    website = token_params.get('website', '')
    
    message += f"• **Twitter:** {twitter if twitter else 'Not provided'}\n"
    message += f"• **Telegram:** {telegram if telegram else 'Not provided'}\n"
    message += f"• **Website:** {website if website else 'Not provided'}\n\n"
    
    message += "🖼️ **Image:** "
    message += "Uploaded" if token_params.get('image_url') else "Not provided"
    message += "\n\n"
    
    message += "✅ Please review your token details and confirm to proceed with creation."
    
    return message

def format_bundle_operation_progress(operation_type: str, progress_data: Dict[str, Any]) -> str:
    """
    Format bundle operation progress message.
    
    Args:
        operation_type: Type of operation (e.g., 'token_creation', 'batch_buy', 'batch_sell')
        progress_data: Progress information
        
    Returns:
        Formatted progress message
    """
    current = progress_data.get('current', 0)
    total = progress_data.get('total', 0)
    status = progress_data.get('status', 'processing')
    current_operation = progress_data.get('current_operation', '')
    
    operation_emoji = {
        'token_creation': '🪙',
        'batch_buy': '🛒',
        'batch_sell': '💸',
        'wallet_funding': '💰'
    }.get(operation_type, '⚙️')
    
    operation_title = {
        'token_creation': 'Token Creation',
        'batch_buy': 'Batch Buy Operation',
        'batch_sell': 'Batch Sell Operation',
        'wallet_funding': 'Wallet Funding'
    }.get(operation_type, 'Bundle Operation')
    
    message = f"{operation_emoji} **{operation_title} Progress**\n\n"
    
    if total > 0:
        progress_bar = "█" * int((current / total) * 10) + "░" * (10 - int((current / total) * 10))
        message += f"📊 **Progress:** {current}/{total} ({(current/total)*100:.1f}%)\n"
        message += f"`{progress_bar}`\n\n"
    
    message += f"⏳ **Status:** {status.title()}\n"
    
    if current_operation:
        message += f"🔄 **Current:** {current_operation}\n"
    
    message += "\n⏱️ Please wait while the operation completes..."
    
    return message

def format_bundle_operation_results(results_data: Dict[str, Any]) -> str:
    """
    Format bundle operation results message.
    
    Args:
        results_data: Results from bundle operation
        
    Returns:
        Formatted results message
    """
    operation_type = results_data.get('operation_type', 'bundle_operation')
    success = results_data.get('success', False)
    total_operations = results_data.get('total_operations', 0)
    successful_operations = results_data.get('successful_operations', 0)
    failed_operations = results_data.get('failed_operations', 0)
    bundle_id = results_data.get('bundle_id', '')
    mint_address = results_data.get('mint_address', '')
    
    operation_emoji = {
        'token_creation': '🪙',
        'batch_buy': '🛒',
        'batch_sell': '💸',
        'wallet_funding': '💰'
    }.get(operation_type, '⚙️')
    
    status_emoji = "✅" if success else "❌"
    
    message = f"{operation_emoji} **Bundle Operation Results** {status_emoji}\n\n"
    
    message += f"📊 **Operation Summary:**\n"
    message += f"• Total operations: {total_operations}\n"
    message += f"• Successful: {successful_operations}\n"
    message += f"• Failed: {failed_operations}\n"
    message += f"• Success rate: {(successful_operations/total_operations)*100:.1f}%\n\n" if total_operations > 0 else ""
    
    if bundle_id:
        message += f"📦 **Bundle ID:** `{bundle_id}`\n"
    
    if mint_address:
        message += f"🪙 **Token Address:** `{mint_address}`\n"
    
    message += "\n"
    
    # Status-specific messaging
    if success:
        if operation_type == 'token_creation':
            message += "🎉 **Token created successfully!**\n"
            message += "Your token is now live on the blockchain."
        elif operation_type == 'batch_buy':
            message += "🎉 **Batch buy completed successfully!**\n"
            message += "All wallets have purchased your token."
        elif operation_type == 'batch_sell':
            message += "🎉 **Batch sell completed successfully!**\n"
            message += "All specified wallets have sold their tokens."
    else:
        message += "⚠️ **Operation completed with issues.**\n"
        message += "Some transactions may have failed. Check the bundle explorer for details."
    
    return message

def format_pumpfun_error_message(error_type: str, error_details: str) -> str:
    """
    Format PumpFun-specific error message.
    
    Args:
        error_type: Type of error (validation, network, bundle, etc.)
        error_details: Detailed error information
        
    Returns:
        Formatted error message
    """
    error_emoji = {
        'validation': '❌',
        'network': '🌐',
        'bundle': '📦',
        'insufficient_balance': '💸',
        'api': '🔧'
    }.get(error_type, '⚠️')
    
    error_title = {
        'validation': 'Validation Error',
        'network': 'Network Error',
        'bundle': 'Bundle Error',
        'insufficient_balance': 'Insufficient Balance',
        'api': 'API Error'
    }.get(error_type, 'Error')
    
    message = f"{error_emoji} **{error_title}**\n\n"
    message += f"📝 **Details:** {error_details}\n\n"
    
    # Provide specific guidance based on error type
    if error_type == 'validation':
        message += "💡 **Solution:**\n"
        message += "• Check your input parameters\n"
        message += "• Ensure all required fields are filled\n"
        message += "• Verify format requirements are met\n"
    elif error_type == 'network':
        message += "💡 **Solution:**\n"
        message += "• Check your internet connection\n"
        message += "• Verify PumpFun API is accessible\n"
        message += "• Try again in a few moments\n"
    elif error_type == 'insufficient_balance':
        message += "💡 **Solution:**\n"
        message += "• Add SOL to your wallets\n"
        message += "• Reduce buy amounts\n"
        message += "• Check wallet balances\n"
    elif error_type == 'bundle':
        message += "💡 **Solution:**\n"
        message += "• Transaction may have failed on-chain\n"
        message += "• Check Solscan for transaction status\n"
        message += "• Consider retrying the operation\n"
    
    message += "\nTry again or contact support if the issue persists."
    
    return message

def format_bundled_wallets_creation_message() -> str:
    """
    Format message for bundled wallets creation step in token bundling flow.
    
    Returns:
        Formatted bundled wallets creation message
    """
    message = "👥 **Bundled Wallets Setup**\n\n"
    message += "Before creating your token, we need to set up the bundled wallets that will participate in the trading.\n\n"
    message += "📝 **What we'll create:**\n"
    message += "• **DevWallet** - Main development wallet for token operations\n"
    message += "• **First Bundled Wallet 1-4** - Initial trading wallets for coordinated buys\n"
    message += "• **Additional Bundled Wallets** - Extra wallets for enhanced trading activity\n\n"
    message += "💡 **Recommended Setup:**\n"
    message += "• Minimum: 5 wallets (1 Dev + 4 Initial)\n"
    message += "• Optimal: 10-20 wallets for better distribution\n"
    message += "• Maximum: 50 wallets for extensive coordination\n\n"
    message += "How many bundled wallets would you like to create? (minimum 5)"
    
    return message

def format_bundled_wallets_created_message(wallet_count: int, wallet_details: List[Dict[str, Any]] = None) -> str:
    """
    Format message confirming bundled wallets creation.
    
    Args:
        wallet_count: Number of wallets created
        wallet_details: Optional list of wallet details
        
    Returns:
        Formatted confirmation message
    """
    message = f"✅ **{wallet_count} Bundled Wallets Created Successfully!**\n\n"
    
    if wallet_details and len(wallet_details) <= 10:  # Show details for small numbers
        message += "📋 **Wallet Overview:**\n"
        for i, wallet in enumerate(wallet_details[:10]):
            name = wallet.get('name', f'Wallet {i+1}')
            address = wallet.get('address', wallet.get('publicKey', 'N/A'))
            short_addr = f"{address[:6]}...{address[-4:]}" if len(address) > 10 else address
            message += f"• **{name}**: `{short_addr}`\n"
        
        if len(wallet_details) > 10:
            message += f"• ... and {len(wallet_details) - 10} more wallets\n"
        message += "\n"
    
    message += "🎯 **Next Steps:**\n"
    message += "• Fund these wallets with SOL for trading operations\n"
    message += "• Configure token parameters for creation\n"
    message += "• Execute coordinated buy/sell operations\n\n"
    message += "Ready to proceed with token creation setup!"
    
    return message

def format_existing_bundled_wallets_choice_message(wallet_count: int, airdrop_wallet_address: str) -> str:
    """
    Format message for choosing between existing and new bundled wallets.
    
    Args:
        wallet_count: Number of existing bundled wallets
        airdrop_wallet_address: The airdrop wallet address
        
    Returns:
        Formatted message string
    """
    short_address = f"{airdrop_wallet_address[:8]}...{airdrop_wallet_address[-8:]}"
    
    return (
        f"🔍 **Existing Bundled Wallets Found**\n\n"
        f"**Airdrop Wallet:** `{short_address}`\n"
        f"**Existing Bundled Wallets:** {wallet_count}\n\n"
        f"You have {wallet_count} bundled wallets already created for this airdrop wallet.\n\n"
        f"Would you like to:"
    )

def format_existing_bundled_wallets_selected_message(wallet_count: int, wallet_addresses: List[str]) -> str:
    """
    Format message confirming selection of existing bundled wallets.
    
    Args:
        wallet_count: Number of selected bundled wallets
        wallet_addresses: List of wallet addresses
        
    Returns:
        Formatted message string
    """
    message = (
        f"✅ **Using Existing Bundled Wallets**\n\n"
        f"**Count:** {wallet_count} wallets\n\n"
        f"**Wallet Addresses:**\n"
    )
    
    # Show first few wallet addresses
    for i, address in enumerate(wallet_addresses[:5]):
        short_address = f"{address[:8]}...{address[-8:]}"
        message += f"  {i+1}. `{short_address}`\n"
    
    if len(wallet_addresses) > 5:
        message += f"  ... and {len(wallet_addresses) - 5} more\n"
    
    message += f"\nReady to proceed with token creation!"
    
    return message