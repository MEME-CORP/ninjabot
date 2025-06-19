"""
Airdrop Wallet Storage Utility

This module provides functionality to store and manage airdrop wallets
for the bundling workflow without interfering with the volume bot's
wallet management system.
"""

import os
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger


class AirdropWalletStorage:
    """Manages storage and retrieval of airdrop wallets for bundling operations."""
    
    def __init__(self, base_data_path: str = "data"):
        """
        Initialize the airdrop wallet storage.
        
        Args:
            base_data_path: Base path for data storage
        """
        self.base_data_path = base_data_path
        self.airdrop_wallets_path = os.path.join(base_data_path, "airdrop_wallets")
        self._ensure_directory_exists()
    
    def _ensure_directory_exists(self) -> None:
        """Ensure the airdrop wallets directory exists."""
        try:
            os.makedirs(self.airdrop_wallets_path, exist_ok=True)
            logger.info(f"Ensured airdrop wallets directory exists: {self.airdrop_wallets_path}")
        except Exception as e:
            logger.error(f"Failed to create airdrop wallets directory: {str(e)}")
            raise
    
    def save_airdrop_wallet(self, wallet_address: str, wallet_data: Dict[str, Any], 
                           user_id: int) -> str:
        """
        Save an airdrop wallet to storage.
        
        Args:
            wallet_address: The wallet's public address
            wallet_data: Complete wallet information
            user_id: Telegram user ID for tracking
            
        Returns:
            The file path where the wallet was saved
        """
        try:
            # Create filename with timestamp and user ID for uniqueness
            timestamp = int(time.time())
            filename = f"airdrop_{user_id}_{timestamp}_{wallet_address[:8]}.json"
            file_path = os.path.join(self.airdrop_wallets_path, filename)
            
            # Prepare wallet data for storage
            storage_data = {
                "wallet_address": wallet_address,
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "timestamp": timestamp,
                "wallet_type": "airdrop",
                "workflow": "bundling",
                **wallet_data  # Include all original wallet data
            }
            
            # Save to file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(storage_data, f, indent=2, ensure_ascii=False)
            
            logger.info(
                f"Saved airdrop wallet for user {user_id}",
                extra={
                    "user_id": user_id,
                    "wallet_address": wallet_address,
                    "file_path": file_path
                }
            )
            
            return file_path
            
        except Exception as e:
            logger.error(
                f"Failed to save airdrop wallet for user {user_id}: {str(e)}",
                extra={"user_id": user_id, "wallet_address": wallet_address}
            )
            raise
    
    def load_airdrop_wallet(self, user_id: int, wallet_address: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Load an airdrop wallet from storage.
        
        Args:
            user_id: Telegram user ID
            wallet_address: Optional specific wallet address to load
            
        Returns:
            Wallet data if found, None otherwise
        """
        try:
            # List all files in the airdrop wallets directory
            if not os.path.exists(self.airdrop_wallets_path):
                return None
            
            files = os.listdir(self.airdrop_wallets_path)
            
            # Filter files for this user
            user_files = [f for f in files if f.startswith(f"airdrop_{user_id}_")]
            
            if not user_files:
                return None
            
            # If specific wallet address requested, find that file
            if wallet_address:
                target_files = [f for f in user_files if wallet_address[:8] in f]
                if not target_files:
                    return None
                user_files = target_files
            
            # Load the most recent file (sorted by timestamp in filename)
            user_files.sort(reverse=True)
            latest_file = user_files[0]
            
            file_path = os.path.join(self.airdrop_wallets_path, latest_file)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                wallet_data = json.load(f)
            
            logger.info(
                f"Loaded airdrop wallet for user {user_id}",
                extra={"user_id": user_id, "file_path": file_path}
            )
            
            return wallet_data
            
        except Exception as e:
            logger.error(
                f"Failed to load airdrop wallet for user {user_id}: {str(e)}",
                extra={"user_id": user_id}
            )
            return None
    
    def list_user_airdrop_wallets(self, user_id: int) -> list:
        """
        List all airdrop wallets for a specific user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            List of wallet data dictionaries
        """
        try:
            if not os.path.exists(self.airdrop_wallets_path):
                return []
            
            files = os.listdir(self.airdrop_wallets_path)
            user_files = [f for f in files if f.startswith(f"airdrop_{user_id}_")]
            
            wallets = []
            for filename in user_files:
                file_path = os.path.join(self.airdrop_wallets_path, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        wallet_data = json.load(f)
                    wallets.append(wallet_data)
                except Exception as e:
                    logger.warning(f"Failed to load wallet file {filename}: {str(e)}")
                    continue
            
            # Sort by timestamp (newest first)
            wallets.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            
            return wallets
            
        except Exception as e:
            logger.error(
                f"Failed to list airdrop wallets for user {user_id}: {str(e)}",
                extra={"user_id": user_id}
            )
            return []


# Global instance for use throughout the application
airdrop_wallet_storage = AirdropWalletStorage() 