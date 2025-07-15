"""
Simple token storage utility for persisting created tokens.
Stores minimal essential data: mint address, creation timestamp, and user ID.
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from loguru import logger


class TokenStorage:
    """Simple file-based storage for created tokens."""
    
    def __init__(self, data_dir: str = "data/tokens"):
        """
        Initialize token storage.
        
        Args:
            data_dir: Directory to store token files
        """
        self.data_dir = data_dir
        self._ensure_data_directory()
    
    def _ensure_data_directory(self) -> None:
        """Ensure the data directory exists."""
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            logger.info(f"Token storage directory ready: {self.data_dir}")
        except Exception as e:
            logger.error(f"Failed to create token storage directory: {e}")
            raise
    
    def _get_user_token_file(self, user_id: int) -> str:
        """Get the token file path for a specific user."""
        return os.path.join(self.data_dir, f"user_{user_id}_tokens.json")
    
    def store_token(self, user_id: int, mint_address: str, 
                   token_name: str = None, bundle_id: str = None) -> bool:
        """
        Store a newly created token.
        
        Args:
            user_id: Telegram user ID
            mint_address: Token mint address from API response
            token_name: Optional token name
            bundle_id: Optional bundle ID from creation
            
        Returns:
            True if stored successfully, False otherwise
        """
        try:
            token_record = {
                "mint_address": mint_address,
                "created_at": datetime.now().isoformat(),
                "user_id": user_id,
                "token_name": token_name,
                "bundle_id": bundle_id
            }
            
            # Load existing tokens for user
            existing_tokens = self.get_user_tokens(user_id)
            
            # Add new token to the list
            existing_tokens.append(token_record)
            
            # Save updated list
            user_file = self._get_user_token_file(user_id)
            with open(user_file, 'w') as f:
                json.dump(existing_tokens, f, indent=2)
            
            logger.info(f"Stored token {mint_address} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store token {mint_address} for user {user_id}: {e}")
            return False
    
    def get_user_tokens(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Get all tokens created by a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            List of token records
        """
        try:
            user_file = self._get_user_token_file(user_id)
            
            if not os.path.exists(user_file):
                return []
            
            with open(user_file, 'r') as f:
                tokens = json.load(f)
            
            # Ensure it's a list
            if not isinstance(tokens, list):
                logger.warning(f"Invalid token file format for user {user_id}, resetting")
                return []
            
            return tokens
            
        except Exception as e:
            logger.error(f"Failed to load tokens for user {user_id}: {e}")
            return []
    
    def get_latest_token(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get the most recently created token for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Latest token record or None if no tokens exist
        """
        tokens = self.get_user_tokens(user_id)
        
        if not tokens:
            return None
        
        # Sort by creation date and return the latest
        try:
            sorted_tokens = sorted(tokens, 
                                 key=lambda x: datetime.fromisoformat(x.get('created_at', '')), 
                                 reverse=True)
            return sorted_tokens[0]
        except Exception as e:
            logger.error(f"Failed to sort tokens for user {user_id}: {e}")
            # Fallback to last item in list
            return tokens[-1]
    
    def token_exists(self, mint_address: str) -> bool:
        """
        Check if a token with given mint address exists in storage.
        
        Args:
            mint_address: Token mint address to check
            
        Returns:
            True if token exists, False otherwise
        """
        try:
            # Check all user token files
            for filename in os.listdir(self.data_dir):
                if filename.startswith('user_') and filename.endswith('_tokens.json'):
                    filepath = os.path.join(self.data_dir, filename)
                    
                    with open(filepath, 'r') as f:
                        tokens = json.load(f)
                    
                    if isinstance(tokens, list):
                        for token in tokens:
                            if token.get('mint_address') == mint_address:
                                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check if token {mint_address} exists: {e}")
            return False


# Global instance
token_storage = TokenStorage()
