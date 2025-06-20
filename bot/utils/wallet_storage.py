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
            logger.info(
                f"Saving {wallet_count} bundled wallets for airdrop wallet {airdrop_wallet_address}",
                extra={
                    "user_id": user_id,
                    "airdrop_wallet_address": airdrop_wallet_address,
                    "wallet_count": wallet_count,
                    "data_keys": list(bundled_wallets_data.keys()) if bundled_wallets_data else []
                }
            )
            
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
            
            # Log the structure being saved for debugging
            logger.debug(
                f"Saving bundled wallets with structure: {list(storage_data.keys())}",
                extra={
                    "user_id": user_id,
                    "airdrop_wallet_address": airdrop_wallet_address,
                    "has_wallets_key": "wallets" in storage_data,
                    "wallets_count_in_data": len(storage_data.get("wallets", [])) if "wallets" in storage_data else 0
                }
            )
            
            # Save to file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(storage_data, f, indent=2, ensure_ascii=False)
            
            logger.info(
                f"Successfully saved {wallet_count} bundled wallets for user {user_id} to {filename}",
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
                extra={"user_id": user_id, "airdrop_wallet_address": airdrop_wallet_address},
                exc_info=True
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
    
    def load_bundled_wallets(self, airdrop_wallet_address: str, user_id: int) -> List[Dict[str, Any]]:
        """
        Load bundled wallets for a specific airdrop wallet and user.
        
        Args:
            airdrop_wallet_address: The airdrop wallet address
            user_id: The user ID
            
        Returns:
            List of bundled wallet data dictionaries
        """
        try:
            logger.info(
                f"Loading bundled wallets for airdrop wallet {airdrop_wallet_address}",
                extra={"user_id": user_id, "airdrop_wallet_address": airdrop_wallet_address}
            )
            
            # Use the existing method to get bundled wallets by airdrop wallet
            wallet_record = self.get_bundled_wallets_by_airdrop(user_id, airdrop_wallet_address)
            
            if not wallet_record:
                logger.info(
                    f"No bundled wallets found for airdrop wallet {airdrop_wallet_address}",
                    extra={"user_id": user_id, "airdrop_wallet_address": airdrop_wallet_address}
                )
                return []
            
            logger.debug(
                f"Found wallet record with keys: {list(wallet_record.keys())}",
                extra={"user_id": user_id, "airdrop_wallet_address": airdrop_wallet_address}
            )
            
            # Extract the wallets from the record - the actual structure uses "data" key
            wallets = []
            
            # The actual saved files use "data" as the key for wallet list
            if "data" in wallet_record and isinstance(wallet_record["data"], list):
                wallets = wallet_record["data"]
                logger.debug(
                    f"Found wallets in 'data' key: {len(wallets)} wallets",
                    extra={"user_id": user_id, "airdrop_wallet_address": airdrop_wallet_address}
                )
            # Fallback to other possible keys for backward compatibility
            elif "wallets" in wallet_record and isinstance(wallet_record["wallets"], list):
                wallets = wallet_record["wallets"]
                logger.debug(
                    f"Found wallets in 'wallets' key: {len(wallets)} wallets",
                    extra={"user_id": user_id, "airdrop_wallet_address": airdrop_wallet_address}
                )
            
            if not wallets:
                logger.warning(
                    f"No wallet data found in record for airdrop wallet {airdrop_wallet_address}",
                    extra={"user_id": user_id, "airdrop_wallet_address": airdrop_wallet_address, "record_keys": list(wallet_record.keys())}
                )
                return []
            
            # Normalize wallet structure - the actual files use "publicKey" and "privateKey"
            valid_wallets = []
            for i, wallet in enumerate(wallets):
                if isinstance(wallet, dict):
                    normalized_wallet = {}
                    
                    # Handle address field - actual files use "publicKey"
                    if "publicKey" in wallet:
                        normalized_wallet["address"] = wallet["publicKey"]
                        normalized_wallet["public_key"] = wallet["publicKey"]  # Keep original too
                    elif "address" in wallet:
                        normalized_wallet["address"] = wallet["address"]
                    elif "public_key" in wallet:
                        normalized_wallet["address"] = wallet["public_key"]
                    else:
                        logger.warning(
                            f"Wallet {i} missing address/publicKey field, skipping",
                            extra={"user_id": user_id, "wallet_keys": list(wallet.keys())}
                        )
                        continue
                    
                    # Handle private key field - actual files use "privateKey"
                    if "privateKey" in wallet:
                        normalized_wallet["private_key"] = wallet["privateKey"]
                    elif "private_key" in wallet:
                        normalized_wallet["private_key"] = wallet["private_key"]
                    elif "secretKey" in wallet:
                        normalized_wallet["private_key"] = wallet["secretKey"]
                    
                    # Keep other fields as-is (name, etc.)
                    for k, v in wallet.items():
                        if k not in ["address", "publicKey", "public_key", "privateKey", "private_key", "secretKey"]:
                            normalized_wallet[k] = v
                    
                    valid_wallets.append(normalized_wallet)
                else:
                    logger.warning(
                        f"Wallet {i} is not a dictionary, skipping: {type(wallet)}",
                        extra={"user_id": user_id}
                    )
            
            logger.info(
                f"Successfully loaded {len(valid_wallets)} bundled wallets for airdrop wallet {airdrop_wallet_address}",
                extra={"user_id": user_id, "airdrop_wallet_address": airdrop_wallet_address, "wallet_count": len(valid_wallets)}
            )
            
            return valid_wallets
            
        except Exception as e:
            logger.error(
                f"Error loading bundled wallets for airdrop wallet {airdrop_wallet_address}: {str(e)}",
                extra={"user_id": user_id, "airdrop_wallet_address": airdrop_wallet_address},
                exc_info=True
            )
            return []


# Global instances for use in handlers
airdrop_wallet_storage = AirdropWalletStorage()
bundled_wallet_storage = BundledWalletStorage() 