"""
Additional message formatters for token storage functionality.
This file contains message formatters that are used alongside the main message_utils.
"""

from typing import Dict, List, Any
from datetime import datetime


def format_token_storage_success_message(token_address: str, token_name: str) -> str:
    """
    Format success message for token storage.
    
    Args:
        token_address: The stored token address
        token_name: The stored token name
        
    Returns:
        Formatted success message
    """
    return (
        f"✅ **Token Stored Successfully**\n\n"
        f"Your created token has been saved to persistent storage:\n\n"
        f"📛 **Name:** {token_name}\n"
        f"📍 **Address:** `{token_address[:8]}...{token_address[-8:]}`\n\n"
        f"You can view your created tokens anytime using the token management features."
    )


def format_user_tokens_list(tokens: List[Dict[str, Any]]) -> str:
    """
    Format a list of user's created tokens.
    
    Args:
        tokens: List of token records
        
    Returns:
        Formatted tokens list message
    """
    if not tokens:
        return (
            "📋 **Your Created Tokens**\n\n"
            "You haven't created any tokens yet.\n\n"
            "Use the token creation feature to get started!"
        )
    
    message = f"📋 **Your Created Tokens** ({len(tokens)} total)\n\n"
    
    for i, token in enumerate(tokens[-10:], 1):  # Show last 10 tokens
        created_at = token.get("created_at", "")
        
        # Parse creation date
        try:
            creation_date = datetime.fromisoformat(created_at).strftime("%Y-%m-%d %H:%M")
        except:
            creation_date = "Unknown"
        
        token_address = token.get("mint_address", "Unknown")
        token_name = token.get("token_name", "Unknown Token")
        
        message += (
            f"**{i}. {token_name}**\n"
            f"└ Address: `{token_address[:8]}...{token_address[-8:]}`\n"
            f"└ Created: {creation_date}\n\n"
        )
    
    if len(tokens) > 10:
        message += f"... and {len(tokens) - 10} more tokens\n\n"
    
    message += "Use the detailed view for complete token information."
    
    return message
