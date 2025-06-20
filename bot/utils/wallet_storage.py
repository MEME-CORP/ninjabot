"""
Airdrop Wallet Storage Utility

This module provides functionality to store and manage airdrop wallets
for the bundling workflow without interfering with the volume bot's
wallet management system.
"""

import os
import json
import time
from typing import Dict, Any, Optional, List
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


class BundledWalletStorage:
    """Manages storage and retrieval of bundled wallets for bundling operations."""
    
    def __init__(self, base_data_path: str = "data"):
        """
        Initialize the bundled wallet storage.
        
        Args:
            base_data_path: Base path for data storage
        """
        self.base_data_path = base_data_path
        self.bundled_wallets_path = os.path.join(base_data_path, "bundled_wallets")
        self._ensure_directory_exists()
    
    def _ensure_directory_exists(self) -> None:
        """Ensure the bundled wallets directory exists."""
        try:
            os.makedirs(self.bundled_wallets_path, exist_ok=True)
            logger.info(f"Ensured bundled wallets directory exists: {self.bundled_wallets_path}")
        except Exception as e:
            logger.error(f"Failed to create bundled wallets directory: {str(e)}")
            raise
    
    def save_bundled_wallets(self, airdrop_wallet_address: str, bundled_wallets_data: Dict[str, Any], 
                           user_id: int, wallet_count: int) -> str:
        """
        Save bundled wallets to storage.
        
        Args:
            airdrop_wallet_address: The airdrop (mother) wallet address
            bundled_wallets_data: Complete bundled wallets information from API
            user_id: Telegram user ID for tracking
            wallet_count: Number of wallets created
            
        Returns:
            The file path where the wallets were saved
        """
        try:
            # Create filename with timestamp and user ID for uniqueness
            timestamp = int(time.time())
            filename = f"bundled_{user_id}_{timestamp}_{airdrop_wallet_address[:8]}.json"
            file_path = os.path.join(self.bundled_wallets_path, filename)
            
            # Prepare wallet data for storage
            storage_data = {
                "airdrop_wallet_address": airdrop_wallet_address,
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "timestamp": timestamp,
                "wallet_type": "bundled",
                "workflow": "bundling",
                "wallet_count": wallet_count,
                **bundled_wallets_data  # Include all original wallet data from API
            }
            
            # Save to file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(storage_data, f, indent=2, ensure_ascii=False)
            
            logger.info(
                f"Saved {wallet_count} bundled wallets for user {user_id}",
                extra={
                    "user_id": user_id,
                    "airdrop_wallet_address": airdrop_wallet_address,
                    "wallet_count": wallet_count,
                    "file_path": file_path
                }
            )
            
            return file_path
            
        except Exception as e:
            logger.error(
                f"Failed to save bundled wallets for user {user_id}: {str(e)}",
                extra={"user_id": user_id, "airdrop_wallet_address": airdrop_wallet_address}
            )
            raise
    
    def list_user_bundled_wallets(self, user_id: int) -> List[Dict[str, Any]]:
        """
        List all bundled wallets saved for a specific user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            List of bundled wallet records
        """
        try:
            user_wallets = []
            
            # Scan all files in the bundled wallets directory
            for filename in os.listdir(self.bundled_wallets_path):
                if filename.startswith(f"bundled_{user_id}_") and filename.endswith(".json"):
                    file_path = os.path.join(self.bundled_wallets_path, filename)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            wallet_data = json.load(f)
                            
                        # Verify this belongs to the user
                        if wallet_data.get("user_id") == user_id:
                            user_wallets.append(wallet_data)
                            
                    except (json.JSONDecodeError, FileNotFoundError) as e:
                        logger.warning(
                            f"Failed to load bundled wallet file {filename}: {str(e)}",
                            extra={"user_id": user_id, "filename": filename}
                        )
                        continue
            
            # Sort by timestamp (newest first)
            user_wallets.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            
            logger.info(
                f"Found {len(user_wallets)} bundled wallet records for user {user_id}",
                extra={"user_id": user_id, "wallet_count": len(user_wallets)}
            )
            
            return user_wallets
            
        except Exception as e:
            logger.error(
                f"Failed to list bundled wallets for user {user_id}: {str(e)}",
                extra={"user_id": user_id}
            )
            return []
    
    def get_bundled_wallets_by_airdrop(self, user_id: int, airdrop_wallet_address: str) -> Optional[Dict[str, Any]]:
        """
        Get bundled wallets associated with a specific airdrop wallet.
        
        Args:
            user_id: Telegram user ID
            airdrop_wallet_address: Airdrop wallet address
            
        Returns:
            Bundled wallets data or None if not found
        """
        try:
            user_wallets = self.list_user_bundled_wallets(user_id)
            
            # Find wallets for the specific airdrop wallet
            for wallet_record in user_wallets:
                if wallet_record.get("airdrop_wallet_address") == airdrop_wallet_address:
                    return wallet_record
            
            logger.info(
                f"No bundled wallets found for airdrop wallet {airdrop_wallet_address}",
                extra={"user_id": user_id, "airdrop_wallet_address": airdrop_wallet_address}
            )
            
            return None
            
        except Exception as e:
            logger.error(
                f"Failed to get bundled wallets for airdrop wallet {airdrop_wallet_address}: {str(e)}",
                extra={"user_id": user_id, "airdrop_wallet_address": airdrop_wallet_address}
            )
            return None


# Global instances for use in handlers
airdrop_wallet_storage = AirdropWalletStorage()
bundled_wallet_storage = BundledWalletStorage() 