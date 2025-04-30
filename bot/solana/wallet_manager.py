"""
Wallet management for Solana.
"""

import base58
import os
import time
from typing import Dict, List, Any, Optional
from solders.keypair import Keypair
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from loguru import logger

from bot.solana.models import WalletInfo

class WalletManager:
    """
    Manages Solana wallets, including creation, derivation, and secure key storage.
    """
    
    def __init__(self, network="devnet"):
        """
        Initialize the wallet manager.
        
        Args:
            network: Solana network to use (devnet or mainnet)
        """
        self.network = network
        # Encryption key derived from a secure random value
        # In a production environment, this would be stored securely
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        self.encryption_key = kdf.derive(os.urandom(32))
        self.aesgcm = AESGCM(self.encryption_key)
        logger.info(f"WalletManager initialized on {network}")
    
    def _encrypt_private_key(self, private_key: bytes) -> bytes:
        """
        Encrypts a private key for secure storage.
        
        Args:
            private_key: The private key as bytes
            
        Returns:
            Encrypted private key
        """
        nonce = os.urandom(12)
        ct = self.aesgcm.encrypt(nonce, private_key, None)
        return nonce + ct
    
    def _decrypt_private_key(self, encrypted_key: bytes) -> bytes:
        """
        Decrypts a stored private key.
        
        Args:
            encrypted_key: The encrypted key
            
        Returns:
            Decrypted private key
        """
        nonce = encrypted_key[:12]
        ct = encrypted_key[12:]
        return self.aesgcm.decrypt(nonce, ct, None)
    
    def create_mother(self) -> WalletInfo:
        """
        Creates a new mother wallet and returns its details.
        
        Returns:
            Wallet information including address and encrypted secret key
        """
        try:
            keypair = Keypair()
            address = str(keypair.pubkey())
            # Encrypt the full 64-byte private key
            full_private_key = bytes(keypair)
            encrypted_key = self._encrypt_private_key(full_private_key)
            
            wallet_info = WalletInfo(
                address=address,
                secret_key=base58.b58encode(encrypted_key).decode('utf-8')
            )
            
            logger.info(f"Created new mother wallet: {address}")
            return wallet_info
            
        except Exception as e:
            # Log the specific error attribute that failed if possible
            logger.error(f"Error creating mother wallet: {str(e)}", exc_info=True)
            raise
    
    def import_mother(self, private_key: str) -> WalletInfo:
        """
        Imports an existing wallet from private key.
        
        Args:
            private_key: Wallet private key (base58 encoded)
            
        Returns:
            Wallet information including address
        """
        try:
            # Decode the base58 private key
            pk_bytes = base58.b58decode(private_key)
            # Use from_bytes to reconstruct the keypair
            keypair = Keypair.from_bytes(pk_bytes) # Changed from from_secret_key
            address = str(keypair.pubkey())
            
            # Encrypt the private key for secure storage
            encrypted_key = self._encrypt_private_key(pk_bytes)
            
            wallet_info = WalletInfo(
                address=address,
                secret_key=base58.b58encode(encrypted_key).decode('utf-8')
            )
            
            logger.info(f"Imported mother wallet: {address}")
            return wallet_info
            
        except ValueError:
            logger.error("Invalid private key format")
            raise ValueError("Invalid private key format. Must be base58 encoded.")
            
        except Exception as e:
            logger.error(f"Error importing wallet: {str(e)}")
            raise
    
    def derive_children(self, n: int, mother_secret: str) -> List[WalletInfo]:
        """
        Deterministically derives n child wallets from mother wallet.
        
        Args:
            n: Number of wallets to derive
            mother_secret: Encrypted mother wallet secret key (base58 encoded)
            
        Returns:
            List of child wallet information
        """
        try:
            # Decrypt the mother wallet private key (this should be the full 64 bytes)
            encrypted_key = base58.b58decode(mother_secret)
            mother_pk_full = self._decrypt_private_key(encrypted_key) # Full 64 bytes
            
            # Use from_bytes to reconstruct the keypair
            mother_keypair = Keypair.from_bytes(mother_pk_full) # Changed from from_secret_key
            
            # Derivation typically uses the 32-byte seed part.
            mother_seed = mother_pk_full[:32] 
            
            child_wallets = []
            for i in range(n):
                # Create deterministic seed based on mother's seed and index
                seed_material = mother_seed + i.to_bytes(4, byteorder='little') # Use derived seed material
                h = hashes.Hash(hashes.SHA256())
                h.update(seed_material)
                derived_seed = h.finalize() # SHA256 produces 32 bytes
                
                # Create child keypair using the derived 32-byte seed
                child_keypair = Keypair.from_seed(derived_seed) 
                address = str(child_keypair.pubkey())
                
                # Encrypt the child's full 64-byte private key
                child_full_private_key = bytes(child_keypair) # Changed from child_keypair.seed
                encrypted_key = self._encrypt_private_key(child_full_private_key)
                
                wallet_info = WalletInfo(
                    address=address,
                    secret_key=base58.b58encode(encrypted_key).decode('utf-8')
                )
                
                child_wallets.append(wallet_info)
            
            logger.info(f"Derived {n} child wallets from {mother_keypair.pubkey()}")
            return child_wallets
            
        except Exception as e:
            logger.error(f"Error deriving child wallets: {str(e)}", exc_info=True)
            raise
    
    def get_keypair(self, encrypted_secret: str) -> Keypair:
        """
        Gets a Keypair object from an encrypted secret key.
        
        Args:
            encrypted_secret: The encrypted secret key (base58 encoded)
            
        Returns:
            Keypair object
        """
        encrypted_key = base58.b58decode(encrypted_secret)
        pk_bytes = self._decrypt_private_key(encrypted_key)
        # Use from_bytes to reconstruct the keypair
        keypair = Keypair.from_bytes(pk_bytes) # Changed from from_secret_key
        return keypair
    
    def clear_keypair_from_memory(self, keypair: Keypair):
        """
        Attempts to clear a keypair from memory (best effort).
        The underlying solders Keypair object might be harder to clear directly.
        
        Args:
            keypair: The keypair to clear
        """
        # Solders Keypair objects are based on Rust structs, making direct
        # memory manipulation like zeroing out attributes difficult/impossible
        # from Python. Relying on Python's garbage collection is the main approach.
        logger.debug(f"Requesting garbage collection for Keypair object {keypair.pubkey()}")
        # Explicitly delete the reference to potentially speed up GC
        del keypair 
        # Note: This doesn't guarantee immediate memory clearing. 

    def import_wallet_from_private_key(self, private_key_b58: str) -> WalletInfo:
        """
        Import a wallet from a raw private key (base58 encoded).

        Args:
            private_key_b58: Base58 encoded private key

        Returns:
            WalletInfo with address and encrypted secret key
        """
        try:
            # Decode the base58 private key
            private_key_bytes = base58.b58decode(private_key_b58)

            # Create a keypair directly using Keypair.from_bytes
            keypair = Keypair.from_bytes(private_key_bytes) # Corrected line

            # Get the public key (address)
            address = str(keypair.pubkey())

            # Encrypt the private key for storage within this session
            # Important: Encrypt the original private_key_bytes, not bytes(keypair)
            # as bytes(keypair) might reconstruct differently in some edge cases.
            encrypted_key = self._encrypt_private_key(private_key_bytes)
            encrypted_key_b58 = base58.b58encode(encrypted_key).decode('utf-8')

            # Return wallet info (with the newly encrypted key for this session)
            return WalletInfo(address=address, secret_key=encrypted_key_b58)
        except Exception as e:
            logger.error(f"Failed to import wallet from private key: {type(e).__name__} - {str(e)}")
            raise 