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

def validate_bundled_wallets_count(text: str) -> Tuple[bool, Union[int, str]]:
    """
    Validate the number of bundled wallets for PumpFun operations.
    
    Args:
        text: The user input text
        
    Returns:
        A tuple of (is_valid, count_or_error_message)
    """
    try:
        count = int(text.strip())
        
        if count < 2:
            return False, "Minimum 2 bundled wallets required for effective bundling."
            
        if count > 20:
            return False, "Maximum 20 bundled wallets allowed per operation."
            
        return True, count
        
    except ValueError:
        return False, "Please enter a valid number of wallets (2-20)."


def validate_token_name(text: str) -> Tuple[bool, Union[str, str]]:
    """
    Validate token name for PumpFun token creation.
    
    Args:
        text: The user input text
        
    Returns:
        A tuple of (is_valid, name_or_error_message)
    """
    name = text.strip()
    
    if len(name) < 2:
        return False, "Token name must be at least 2 characters long."
    
    if len(name) > 32:
        return False, "Token name cannot exceed 32 characters."
    
    # Allow alphanumeric, spaces, and common symbols
    if not re.match(r'^[a-zA-Z0-9\s\-_\.]+$', name):
        return False, "Token name can only contain letters, numbers, spaces, hyphens, underscores, and periods."
    
    return True, name


def validate_token_ticker(text: str) -> Tuple[bool, Union[str, str]]:
    """
    Validate token ticker/symbol for PumpFun token creation.
    
    Args:
        text: The user input text
        
    Returns:
        A tuple of (is_valid, ticker_or_error_message)
    """
    ticker = text.strip().upper()
    
    if len(ticker) < 2:
        return False, "Token ticker must be at least 2 characters long."
    
    if len(ticker) > 10:
        return False, "Token ticker cannot exceed 10 characters."
    
    # Only allow alphanumeric characters
    if not re.match(r'^[A-Z0-9]+$', ticker):
        return False, "Token ticker can only contain letters and numbers."
    
    return True, ticker


def validate_token_description(text: str) -> Tuple[bool, Union[str, str]]:
    """
    Validate token description for PumpFun token creation.
    
    Args:
        text: The user input text
        
    Returns:
        A tuple of (is_valid, description_or_error_message)
    """
    description = text.strip()
    
    if len(description) < 10:
        return False, "Token description must be at least 10 characters long."
    
    if len(description) > 500:
        return False, "Token description cannot exceed 500 characters."
    
    return True, description


def validate_image_url(text: str) -> Tuple[bool, Union[str, str]]:
    """
    Validate image URL for PumpFun token creation.
    
    Args:
        text: The user input text
        
    Returns:
        A tuple of (is_valid, url_or_error_message)
    """
    url = text.strip()
    
    # Allow empty URL (optional field)
    if not url:
        return True, ""
    
    # Basic URL validation
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    if not url_pattern.match(url):
        return False, "Please enter a valid HTTP/HTTPS URL for the token image."
    
    # Check for common image extensions
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']
    if not any(url.lower().endswith(ext) for ext in valid_extensions):
        return False, "Image URL should end with a valid image extension (.jpg, .png, .gif, etc.)"
    
    return True, url


def validate_token_supply(text: str) -> Tuple[bool, Union[int, str]]:
    """
    Validate token initial supply for PumpFun token creation.
    
    Args:
        text: The user input text
        
    Returns:
        A tuple of (is_valid, supply_or_error_message)
    """
    try:
        # Remove commas and clean the input
        cleaned_text = text.replace(",", "").strip()
        supply = int(cleaned_text)
        
        if supply < 1000:
            return False, "Token supply must be at least 1,000 tokens."
        
        if supply > 1_000_000_000_000:  # 1 trillion
            return False, "Token supply cannot exceed 1,000,000,000,000 tokens."
        
        return True, supply
        
    except ValueError:
        return False, "Please enter a valid number for token supply (e.g., 1000000 for 1 million tokens)."


def log_validation_result(validation_type: str, input_value: str, is_valid: bool, error_message: str, user_id: int = None):
    """
    Log validation results for metrics and debugging.
    
    Args:
        validation_type: Type of validation being performed
        input_value: The original input value
        is_valid: Whether the validation passed
        error_message: Error message if validation failed
        user_id: Optional Telegram user ID
    """
    if is_valid:
        logger.debug(
            f"Validation passed: {validation_type}",
            extra={
                "user_id": user_id,
                "validation_type": validation_type,
                "input_value": input_value[:50] + "..." if len(str(input_value)) > 50 else input_value
            }
        )
    else:
        logger.info(
            f"Validation failed: {validation_type}",
            extra={
                "user_id": user_id,
                "validation_type": validation_type,
                "input_value": input_value[:50] + "..." if len(str(input_value)) > 50 else input_value,
                "error": error_message
            }
        ) 