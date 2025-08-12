import json
import os
from typing import Dict, List, Any, Optional
from loguru import logger

def load_mother_wallets_from_folder(data_dir: str) -> List[Dict[str, Any]]:
    """
    Load mother wallets from the mother_wallets folder.
    
    Args:
        data_dir: The data directory path
        
    Returns:
        List of wallet data dictionaries
    """
    wallets = []
    
    # Check mother_wallets directory
    mother_dir = os.path.join(data_dir, 'mother_wallets')
    if not os.path.exists(mother_dir):
        return wallets
    
    try:
        # Get all JSON files in the mother_wallets directory
        wallet_files = [f for f in os.listdir(mother_dir) if f.endswith('.json')]
        
        for filename in wallet_files:
            try:
                file_path = os.path.join(mother_dir, filename)
                with open(file_path, 'r') as f:
                    wallet_data = json.load(f)
                    
                # Ensure wallet has required fields
                if isinstance(wallet_data, dict) and 'address' in wallet_data:
                    # Add metadata for identification
                    wallet_data['file_path'] = file_path
                    wallet_data['file_name'] = filename
                    wallets.append(wallet_data)
                    logger.info(f"Loaded mother wallet from {filename}: {wallet_data.get('address', 'unknown')[:8]}...")
                    
            except Exception as e:
                logger.warning(f"Error loading mother wallet file {filename}: {str(e)}")
                continue
    
    except Exception as e:
        logger.error(f"Error reading mother_wallets directory: {str(e)}")
    
    return wallets
