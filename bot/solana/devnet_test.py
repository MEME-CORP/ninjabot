"""
Devnet testing script for Solana volume bot.

This script demonstrates the complete workflow of the Solana volume bot on devnet.
It creates wallets, funds them, generates a schedule, and executes transfers.
"""

import os
import asyncio
import time
import argparse
import base58
from datetime import datetime, timedelta
import requests
from loguru import logger
from pathlib import Path
from dotenv import load_dotenv, set_key
import json

from bot.solana import (
    WalletInfo,
    WalletManager,
    FeeOracle,
    Scheduler,
    FeeCollector,
    TxExecutor,
    SolanaVolumeOrchestrator
)
from bot.solana.integration import SolanaVolumeOrchestrator # Ensure this is imported if not already

# Configure logging
logger.add("logs/devnet_test.log", rotation="50 MB", level="INFO")

# Load environment variables
load_dotenv()

# Devnet faucet endpoint
DEVNET_FAUCET_URL = "https://faucet.devnet.solana.com/api/v1/fund"

# Environment variable name for mother wallet - changing the approach entirely
MOTHER_WALLET_KEY = "SOLANA_MOTHER_WALLET_PRIVATE_KEY"
ENV_FILE_PATH = Path(".env")

def save_wallet_to_env(wallet_info: WalletInfo, wallet_manager: WalletManager):
    """
    Save the raw private key to .env file for reuse.
    
    Args:
        wallet_info: The wallet information containing the encrypted secret key
        wallet_manager: The wallet manager instance for decryption
    """
    try:
        # Get the encrypted key bytes
        encrypted_key_bytes = base58.b58decode(wallet_info.secret_key)
        
        # Decrypt to get the raw private key
        raw_key_bytes = wallet_manager._decrypt_private_key(encrypted_key_bytes)
        
        # Convert to base58 for storage
        raw_key_b58 = base58.b58encode(raw_key_bytes).decode('utf-8')
        
        # Store the raw private key directly
        set_key(str(ENV_FILE_PATH), MOTHER_WALLET_KEY, raw_key_b58)
        logger.info(f"Saved mother wallet's private key to .env")
    except Exception as e:
        logger.error(f"Error saving wallet to .env: {type(e).__name__} - {str(e)}")

def load_wallet_from_env(wallet_manager: WalletManager) -> WalletInfo:
    """
    Load mother wallet from .env file if available, or create a new one.

    Args:
        wallet_manager: The WalletManager instance.

    Returns:
        Loaded or created wallet information.
    """
    # Get raw private key from env (no quotes)
    raw_private_key = os.getenv(MOTHER_WALLET_KEY)
    
    if raw_private_key:
        try:
            # Remove any quotes if present in the .env file
            raw_private_key = raw_private_key.strip("'\"")
            
            # Log attempt without revealing full key
            logger.info(f"Attempting to load mother wallet with raw private key")
            
            # Import the wallet directly using raw private key
            wallet_info = wallet_manager.import_wallet_from_private_key(raw_private_key)
            
            logger.info(f"Successfully loaded mother wallet: {wallet_info.address}")
            print(f"Loaded existing mother wallet: {wallet_info.address}")
            print(f"Private key (base58): {raw_private_key}")
            
            return wallet_info
            
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e) if str(e) else "Unknown error"
            logger.error(f"Error loading wallet from private key: [{error_type}] {error_msg}")
    
    # Create new wallet if loading failed
    logger.info("Creating a new mother wallet")
    wallet_info = wallet_manager.create_mother()
    
    # Display and save the wallet info
    try:
        encrypted_key_bytes = base58.b58decode(wallet_info.secret_key)
        raw_pk_bytes = wallet_manager._decrypt_private_key(encrypted_key_bytes)
        raw_pk_b58 = base58.b58encode(raw_pk_bytes).decode('utf-8')
        
        print(f"Created new mother wallet: {wallet_info.address}")
        print(f"Private key (base58): {raw_pk_b58}")
        
        # Save the raw private key
        save_wallet_to_env(wallet_info, wallet_manager)
        
    except Exception as decrypt_err:
        logger.warning(f"Could not display/save private key: {type(decrypt_err).__name__} - {str(decrypt_err)}")
    
    return wallet_info

async def request_airdrop(wallet_address: str, amount_sol: float = 1.0) -> bool:
    """
    Request an airdrop of SOL from the devnet faucet.
    
    Args:
        wallet_address: Wallet address to fund
        amount_sol: Amount of SOL to request (default 1.0)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Requesting {amount_sol} SOL airdrop for {wallet_address}")
        
        # Convert SOL to lamports
        lamports = int(amount_sol * 1e9)
        
        response = requests.post(
            DEVNET_FAUCET_URL,
            json={
                "recipient": wallet_address,
                "lamports": lamports
            }
        )
        
        if response.status_code == 200:
            logger.info(f"Airdrop request successful for {wallet_address}")
            return True
        else:
            logger.error(f"Airdrop request failed: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error requesting airdrop: {str(e)}")
        return False

async def fund_wallets(mother_wallet: WalletInfo, child_wallets: list[WalletInfo]) -> bool:
    """
    Display instructions for funding wallets manually through Solana's faucet.
    
    Args:
        mother_wallet: Mother wallet info
        child_wallets: List of child wallet info
        
    Returns:
        True if user confirms funding was completed
    """
    # Instructions for manual funding
    print("\n===== MANUAL WALLET FUNDING REQUIRED =====")
    print("Please request SOL from the Solana Devnet Faucet:")
    print("1. Go to: https://faucet.solana.com/")
    print("2. Make sure 'Devnet' is selected")
    print("3. Enter the following address to fund the mother wallet:")
    print(f"   {mother_wallet.address}")
    print("4. Request at least 2 SOL for the mother wallet")
    
    if len(child_wallets) > 0:
        print("\nOptionally, you may also fund some child wallets:")
        for i in range(min(5, len(child_wallets))):
            print(f"   Child wallet {i+1}: {child_wallets[i].address}")
    
    # Wait for user confirmation
    user_input = input("\nPress Enter after completing the funding to continue, or type 'skip' to skip funding check: ")
    
    if user_input.lower() == 'skip':
        print("Skipping funding check. Note that transfers might fail if wallets aren't properly funded.")
        return True
    
    # Wait a bit for transaction confirmations
    print("Waiting for transaction confirmations...")
    await asyncio.sleep(10)
    
    print("Continuing with the test. If transfers fail, the wallets may not have enough SOL.")
    return True

def print_transfer_schedule(schedule):
    """Print a readable format of the transfer schedule."""
    print("\n=== TRANSFER SCHEDULE ===")
    print(f"Schedule ID: {schedule.id}")
    print(f"Total volume: {schedule.total_volume} SOL")
    print(f"Service fee: {schedule.service_fee_total} SOL")
    print(f"Total transfers: {len(schedule.transfers)}")
    
    print("\nTransfers:")
    transfers = sorted(schedule.transfers, key=lambda t: t.estimated_time)
    for i, transfer in enumerate(transfers[:10]):  # Show first 10 transfers
        print(f"  {i+1}. {transfer.from_address[:8]}... → {transfer.to_address[:8]}... : {transfer.amount:.4f} SOL @ {transfer.estimated_time.strftime('%H:%M:%S')}")
    
    if len(transfers) > 10:
        print(f"  ... and {len(transfers) - 10} more transfers")

def register_event_handlers(orchestrator):
    """Register event handlers for transaction events."""
    
    def on_tx_sent(data):
        tx_hash = data.get("tx_hash", "unknown")
        print(f"🚀 Transaction sent: {tx_hash[:12]}...")
    
    def on_tx_confirmed(data):
        tx_hash = data.get("tx_hash", "unknown")
        print(f"✅ Transaction confirmed: {tx_hash[:12]}...")
    
    def on_tx_failed(data):
        tx_hash = data.get("tx_hash", "unknown")
        error = data.get("error", "unknown error")
        print(f"❌ Transaction failed: {tx_hash[:12]}... - {error}")
    
    def on_tx_retry(data):
        tx_hash = data.get("tx_hash", "unknown")
        retry_count = data.get("retry_count", 0)
        print(f"🔄 Retrying transaction: {tx_hash[:12]}... (attempt {retry_count})")
    
    def on_schedule_started(data):
        schedule_id = data.get("schedule_id", "unknown")
        print(f"📋 Schedule execution started: {schedule_id[:8]}...")
    
    def on_schedule_completed(data):
        schedule_id = data.get("schedule_id", "unknown")
        status = data.get("status", "unknown")
        print(f"🏁 Schedule execution completed: {schedule_id[:8]}... (status: {status})")
    
    # Register all callbacks
    orchestrator.register_event_callback("on_tx_sent", on_tx_sent)
    orchestrator.register_event_callback("on_tx_confirmed", on_tx_confirmed)
    orchestrator.register_event_callback("on_tx_failed", on_tx_failed)
    orchestrator.register_event_callback("on_tx_retry", on_tx_retry)
    orchestrator.register_event_callback("on_schedule_started", on_schedule_started)
    orchestrator.register_event_callback("on_schedule_completed", on_schedule_completed)

async def run_devnet_test(n_wallets: int = 5, volume: float = 0.1, token_mint: str = None):
    """
    Run a complete devnet test of the Solana volume bot.
    
    Args:
        n_wallets: Number of child wallets to create
        volume: Total volume to transfer in SOL
        token_mint: Token mint address (if None, use native SOL)
    """
    print("🚀 Starting Solana Volume Bot Devnet Test")
    print("=========================================")
    
    # Use native SOL for testing if no token mint is provided
    if not token_mint:
        token_mint = "11111111111111111111111111111111"  # Native SOL
        print("Using native SOL for transfers")
    
    # === Instantiate WalletManager ONCE ===
    wallet_manager = WalletManager(network="devnet")

    # Create service wallet using the single instance
    service_wallet = wallet_manager.create_mother()
    print(f"Created service wallet: {service_wallet.address}")

    # Initialize orchestrator, PASSING the single WalletManager instance
    orchestrator = SolanaVolumeOrchestrator(
        network="devnet",
        service_wallet=service_wallet.address,
        wallet_manager=wallet_manager # Pass the instance here
    )

    # Register event handlers (orchestrator uses the passed wallet_manager)
    register_event_handlers(orchestrator)

    # Load or create mother wallet using the single instance
    print("\n📝 Loading/Creating mother wallet...")
    # Pass the single wallet_manager instance
    mother_wallet = load_wallet_from_env(wallet_manager)

    # Derive child wallets (orchestrator uses the passed wallet_manager)
    child_wallets = orchestrator.derive_child_wallets(
        n=n_wallets,
        mother_secret=mother_wallet.secret_key
    )
    print(f"Derived {len(child_wallets)} child wallets")
    
    # Extract child addresses
    child_addresses = [w.address for w in child_wallets]
    
    # Fund wallets - manual instructions remain unchanged
    print("\n💰 Funding wallets on devnet (manual step)...")
    funded = await fund_wallets(mother_wallet, child_wallets)
    if not funded:
        print("❌ Wallet funding process was interrupted, aborting test")
        return
    
    # Generate schedule - compress timeframe for testing (transfers every 10-20 seconds)
    print("\n📋 Generating transfer schedule...")
    schedule = orchestrator.generate_schedule(
        mother_wallet=mother_wallet.address,
        child_wallets=child_addresses,
        token_mint=token_mint,
        total_volume=volume
    )
    
    # Adjust schedule for testing - make transfers happen sooner
    now = datetime.now()
    for i, transfer in enumerate(schedule.transfers):
        # Schedule transfers 10-20 seconds apart
        transfer.estimated_time = now + timedelta(seconds=10 + (i * 10))
    
    # Print schedule
    print_transfer_schedule(schedule)
    
    # Prepare wallet secrets for transaction execution
    wallet_secrets = {
        mother_wallet.address: mother_wallet.secret_key,
        service_wallet.address: service_wallet.secret_key
    }
    
    for wallet in child_wallets:
        wallet_secrets[wallet.address] = wallet.secret_key
    
    # Execute schedule
    print("\n▶️ Executing transfer schedule...")
    updated_schedule = await orchestrator.execute_schedule(schedule, wallet_secrets)
    
    # Print results
    print("\n===== Test Results =====")
    total_transfers = len(updated_schedule.transfers)
    completed_transfers = sum(1 for t in updated_schedule.transfers if t.status == "completed")
    failed_transfers = sum(1 for t in updated_schedule.transfers if t.status == "failed")
    
    print(f"Total transfers: {total_transfers}")
    print(f"Completed transfers: {completed_transfers}")
    print(f"Failed transfers: {failed_transfers}")
    print(f"Success rate: {(completed_transfers / total_transfers) * 100:.1f}%")
    
    if updated_schedule.status == "completed":
        print("\n✅ TEST COMPLETED SUCCESSFULLY")
    else:
        print("\n⚠️ TEST COMPLETED WITH ERRORS")
    
    return updated_schedule

async def main():
    """Parse arguments and run the test."""
    parser = argparse.ArgumentParser(description="Run Solana Volume Bot devnet test")
    parser.add_argument("--wallets", type=int, default=5, help="Number of child wallets to create")
    parser.add_argument("--volume", type=float, default=0.1, help="Total volume to transfer in SOL")
    parser.add_argument("--token", type=str, default=None, help="SPL token mint address (if not provided, uses native SOL)")
    
    args = parser.parse_args()
    
    try:
        await run_devnet_test(
            n_wallets=args.wallets,
            volume=args.volume,
            token_mint=args.token
        )
    except Exception as e:
        logger.exception(f"Test failed with error: {str(e)}")
        print(f"\n❌ TEST FAILED: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 