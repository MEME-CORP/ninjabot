import re
from typing import Tuple, Union
from loguru import logger
from bot.config import MIN_CHILD_WALLETS, MAX_CHILD_WALLETS, MIN_VOLUME, SOLANA_ADDRESS_LENGTH

def validate_child_wallets_input(text: str) -> Tuple[bool, Union[int, str]]:
    """
    Validate the number of child wallets input.
    
    Args:
        text: The user input text
        
    Returns:
        A tuple of (is_valid, value_or_error_message)
    """
    try:
        value = int(text.strip())
        
        if value < MIN_CHILD_WALLETS:
            return False, f"Number of child wallets must be at least {MIN_CHILD_WALLETS}."
            
        if value > MAX_CHILD_WALLETS:
            return False, f"Number of child wallets cannot exceed {MAX_CHILD_WALLETS}."
            
        return True, value
        
    except ValueError:
        return False, "Please enter a valid number."
        
def validate_volume_input(text: str) -> Tuple[bool, Union[float, str]]:
    """
    Validate user input for volume amount.
    
    Args:
        text: User input text
        
    Returns:
        Tuple (is_valid, value_or_error)
    """
    try:
        # Remove commas and currency signs if present
        cleaned_text = text.replace(",", "").replace("$", "").strip()
        
        # Try to convert to float
        volume = float(cleaned_text)
        
        # Check if positive
        if volume <= 0:
            return False, "Volume must be a positive number in SOL."
        
        # Check if within reasonable range
        if volume < MIN_VOLUME:
            return False, f"Volume must be at least {MIN_VOLUME} SOL."
        
        if volume > 1000000000:  # Billion SOL limit
            return False, "Volume cannot exceed 1,000,000,000 SOL."
        
        # Return as integer if it's a whole number, otherwise as float
        return True, int(volume) if volume.is_integer() else volume
        
    except ValueError:
        return False, "Please enter a valid number in SOL (e.g., 0.5 for 0.5 SOL)."

def validate_token_address(text: str) -> Tuple[bool, Union[str, str]]:
    """
    Validate a Solana token address.
    
    Args:
        text: The user input text
        
    Returns:
        A tuple of (is_valid, address_or_error_message)
    """
    # Remove spaces
    address = text.strip()
    
    # Check length
    if len(address) != SOLANA_ADDRESS_LENGTH:
        return False, f"Solana token addresses should be {SOLANA_ADDRESS_LENGTH} characters. Please enter a valid address."
    
    # Base58 character set (simplified check)
    if not re.match(r'^[1-9A-HJ-NP-Za-km-z]+$', address):
        return False, "Invalid characters in address. Solana addresses use Base58 encoding."
    
    return True, address
    
def validate_wallet_address(text: str) -> Tuple[bool, Union[str, str]]:
    """
    Validate a Solana wallet address.
    
    Args:
        text: The user input text
        
    Returns:
        A tuple of (is_valid, address_or_error_message)
    """
    # For the sake of this implementation, wallet validation is the same as token
    return validate_token_address(text)

def log_validation_result(user_id: int, validation_type: str, is_valid: bool, value_or_error: Union[str, int, float]):
    """
    Log validation results for metrics and debugging.
    
    Args:
        user_id: Telegram user ID
        validation_type: Type of validation being performed
        is_valid: Whether the validation passed
        value_or_error: The parsed value or error message
    """
    if is_valid:
        logger.debug(
            f"Validation passed: {validation_type}",
            extra={
                "user_id": user_id,
                "validation_type": validation_type,
                "value": value_or_error
            }
        )
    else:
        logger.info(
            f"Validation failed: {validation_type}",
            extra={
                "user_id": user_id,
                "validation_type": validation_type,
                "error": value_or_error
            }
        ) 