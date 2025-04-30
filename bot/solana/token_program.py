"""
SPL Token program utilities for Solana.

This module provides functions for working with SPL tokens on Solana.
"""

import base58
from typing import Dict, Any, Optional
from solders.pubkey import Pubkey
from solana.transaction import Transaction
from solders.instruction import Instruction, AccountMeta
from solders.keypair import Keypair
from solana.rpc.api import Client
from solana.rpc.async_api import AsyncClient
from loguru import logger

# SPL Token Program ID
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

# SPL Token Program Instruction Codes
TRANSFER_INSTRUCTION = 3  # Token Program instruction index for transfer

class TokenError(Exception):
    """Base exception for token-related errors."""
    pass

def get_token_account(
    rpc_client: Client, 
    wallet_address: str, 
    token_mint: str
) -> Optional[str]:
    """
    Find a token account for a wallet and token mint.
    
    Args:
        rpc_client: Solana RPC client
        wallet_address: Wallet address to find token account for
        token_mint: Token mint address
        
    Returns:
        Token account address or None if not found
    """
    try:
        response = rpc_client.get_token_accounts_by_owner(
            wallet_address,
            {"mint": token_mint}
        )
        
        if "result" in response and "value" in response["result"] and response["result"]["value"]:
            return response["result"]["value"][0]["pubkey"]
        
        logger.warning(
            f"No token account found for wallet {wallet_address} and mint {token_mint}",
            extra={"wallet": wallet_address, "token_mint": token_mint}
        )
        
        return None
        
    except Exception as e:
        logger.error(
            f"Error getting token account: {str(e)}",
            extra={"wallet": wallet_address, "token_mint": token_mint}
        )
        return None

def create_token_account_instruction(
    payer_keypair: Keypair,
    wallet_address: str,
    token_mint: str
) -> Dict[str, Any]:
    """
    Create an instruction to create a token account.
    
    Args:
        payer_keypair: Keypair that will pay for the transaction
        wallet_address: Wallet address to create token account for
        token_mint: Token mint address
        
    Returns:
        Dictionary with instructions and associated keypairs
    """
    # This is a placeholder for a more complex implementation
    # Creating a token account requires multiple instructions and is more complex
    logger.warning("Token account creation not fully implemented")
    return {"instructions": [], "signers": []}

def create_token_transfer_instruction(
    sender_token_account: str,
    recipient_token_account: str,
    owner_address: str,
    amount: int
) -> Instruction:
    """
    Create an SPL token transfer instruction.
    
    Args:
        sender_token_account: Sender's token account (string address)
        recipient_token_account: Recipient's token account (string address)
        owner_address: Owner of the sending token account (string address)
        amount: Amount to transfer in smallest units (e.g., lamports)
        
    Returns:
        Instruction for the token transfer
    """
    keys = [
        AccountMeta(pubkey=Pubkey.from_string(sender_token_account), is_signer=False, is_writable=True),
        AccountMeta(pubkey=Pubkey.from_string(recipient_token_account), is_signer=False, is_writable=True),
        AccountMeta(pubkey=Pubkey.from_string(owner_address), is_signer=True, is_writable=False)
    ]
    
    data = bytes([TRANSFER_INSTRUCTION]) + amount.to_bytes(8, byteorder='little')
    
    return Instruction(
        keys=keys,
        program_id=Pubkey.from_string(TOKEN_PROGRAM_ID),
        data=data
    )

async def execute_token_transfer(
    async_client: AsyncClient,
    sender_keypair: Keypair,
    sender_token_account: str,
    recipient_token_account: str,
    amount: int,
    recent_blockhash: str
) -> Dict[str, Any]:
    """
    Execute an SPL token transfer.
    
    Args:
        async_client: Async Solana RPC client
        sender_keypair: Keypair of the sending wallet
        sender_token_account: Sender's token account
        recipient_token_account: Recipient's token account
        amount: Amount to transfer in smallest units (e.g., lamports)
        recent_blockhash: Recent blockhash for the transaction
        
    Returns:
        Dictionary with transaction result
    """
    try:
        # Create transaction
        tx = Transaction()
        tx.recent_blockhash = recent_blockhash
        tx.fee_payer = sender_keypair.public_key
        
        # Add transfer instruction
        tx.add(
            create_token_transfer_instruction(
                sender_token_account=sender_token_account,
                recipient_token_account=recipient_token_account,
                # Pass owner address as a string
                owner_address=str(sender_keypair.public_key),
                amount=amount
            )
        )
        
        # Sign transaction
        tx.sign(sender_keypair)
        
        # Serialize and send transaction
        serialized_tx = tx.serialize()
        tx_bytes = base58.b58encode(serialized_tx).decode('utf-8')
        
        response = await async_client.send_raw_transaction(tx_bytes)
        
        if "result" in response:
            return {
                "success": True,
                "tx_hash": response["result"],
                "error": None
            }
        else:
            error = response.get("error", {}).get("message", "Unknown error")
            logger.error(f"Token transfer error: {error}")
            return {
                "success": False,
                "tx_hash": None,
                "error": error
            }
            
    except Exception as e:
        logger.exception(f"Error executing token transfer: {str(e)}")
        return {
            "success": False,
            "tx_hash": None,
            "error": str(e)
        }

async def wait_for_token_transfer_confirmation(
    async_client: AsyncClient,
    tx_hash: str,
    timeout_seconds: int = 30
) -> bool:
    """
    Wait for token transfer confirmation.
    
    Args:
        async_client: Async Solana RPC client
        tx_hash: Transaction hash to check
        timeout_seconds: Timeout in seconds
        
    Returns:
        True if confirmed, False otherwise
    """
    import time
    import asyncio
    
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        try:
            response = await async_client.get_signature_statuses([tx_hash])
            
            if "result" in response and response["result"]["value"][0]:
                status = response["result"]["value"][0]
                
                if status.get("confirmations") is None and status.get("confirmationStatus") == "finalized":
                    return True
                
                if status.get("err"):
                    logger.error(f"Transaction error: {status.get('err')}")
                    return False
            
            # Wait before checking again
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error checking token transfer status: {str(e)}")
            await asyncio.sleep(2)
    
    logger.warning(f"Token transfer confirmation timeout for {tx_hash}")
    return False 