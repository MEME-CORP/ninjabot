"""
Configuration module for SPL Token Buy/Sell Script.
Provides configuration classes, validation, and default settings.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Union
from enum import Enum
import json
import time
from pathlib import Path

from loguru import logger


class OperationType(Enum):
    """Supported swap operations."""
    BUY = "buy"
    SELL = "sell"


class AmountStrategy(Enum):
    """Strategies for calculating swap amounts per wallet."""
    FIXED = "fixed"          # Same amount for all wallets
    PERCENTAGE = "percentage" # Percentage of wallet balance
    RANDOM = "random"        # Random amount within range
    CUSTOM = "custom"        # Custom amounts per wallet


class ExecutionMode(Enum):
    """Execution modes for multi-wallet operations."""
    SEQUENTIAL = "sequential"  # One wallet at a time
    PARALLEL = "parallel"     # Multiple wallets concurrently
    BATCH = "batch"          # Batched execution with delays


@dataclass
class TokenConfig:
    """Configuration for token pairs and validation."""
    input_token: str  # Token symbol or mint address
    output_token: str  # Token symbol or mint address
    input_mint: Optional[str] = None  # Resolved mint address
    output_mint: Optional[str] = None  # Resolved mint address
    
    def __post_init__(self):
        """Validate token configuration."""
        # Allow empty tokens during initialization for step-by-step configuration
        if self.input_token and self.output_token:
            if self.input_token == self.output_token:
                raise ValueError("Input and output tokens cannot be the same")
    
    def validate_complete(self):
        """Validate that configuration is complete and ready for execution."""
        if not self.input_token or not self.output_token:
            raise ValueError("Both input_token and output_token must be specified")
        
        if self.input_token == self.output_token:
            raise ValueError("Input and output tokens cannot be the same")


@dataclass
class AmountConfig:
    """Configuration for amount calculation strategies."""
    strategy: AmountStrategy
    base_amount: Optional[float] = None  # For FIXED strategy
    percentage: Optional[float] = None   # For PERCENTAGE strategy (0.0-1.0)
    min_amount: Optional[float] = None   # For RANDOM strategy
    max_amount: Optional[float] = None   # For RANDOM strategy
    custom_amounts: Optional[List[float]] = None  # For CUSTOM strategy
    
    def __post_init__(self):
        """Validate amount configuration based on strategy."""
        if self.strategy == AmountStrategy.FIXED:
            if self.base_amount is None or self.base_amount <= 0:
                raise ValueError("FIXED strategy requires positive base_amount")
        
        elif self.strategy == AmountStrategy.PERCENTAGE:
            if self.percentage is None or not (0.0 < self.percentage <= 1.0):
                raise ValueError("PERCENTAGE strategy requires percentage between 0.0 and 1.0")
        
        elif self.strategy == AmountStrategy.RANDOM:
            if (self.min_amount is None or self.max_amount is None or 
                self.min_amount <= 0 or self.max_amount <= 0 or 
                self.min_amount >= self.max_amount):
                raise ValueError("RANDOM strategy requires valid min_amount < max_amount > 0")
        
        elif self.strategy == AmountStrategy.CUSTOM:
            if not self.custom_amounts or not all(amt > 0 for amt in self.custom_amounts):
                raise ValueError("CUSTOM strategy requires list of positive amounts")


@dataclass
class ExecutionConfig:
    """Configuration for execution parameters."""
    mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    max_concurrent: int = 5
    batch_size: int = 10
    delay_between_batches: float = 2.0
    delay_between_swaps: float = 0.5
    slippage_bps: int = 50  # 0.5%
    verify_swaps: bool = True
    collect_fees: bool = True
    retry_failed: bool = True
    max_retries: int = 3
    
    def __post_init__(self):
        """Validate execution configuration."""
        if self.max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        
        if self.slippage_bps < 0 or self.slippage_bps > 10000:
            raise ValueError("slippage_bps must be between 0 and 10000")
        
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")


@dataclass
class SwapConfiguration:
    """Main configuration class for the buy/sell script."""
    operation: OperationType
    token_config: TokenConfig
    amount_config: AmountConfig
    execution_config: ExecutionConfig = field(default_factory=ExecutionConfig)
    
    # Wallet configuration
    mother_wallet_address: Optional[str] = None
    use_saved_wallets: bool = True
    wallet_selection: str = "all"  # "all", "random", "first_n", "custom"
    wallet_count: Optional[int] = None  # For "random" or "first_n"
    custom_wallet_indices: Optional[List[int]] = None  # For "custom"
    
    # Reporting and logging
    generate_report: bool = True
    report_format: str = "json"  # "json", "csv", "yaml"
    log_level: str = "INFO"
    save_results: bool = True
    
    # Safety and validation
    dry_run: bool = False
    confirm_before_execution: bool = True
    balance_check_threshold: float = 0.001  # Minimum SOL balance required
    
    def __post_init__(self):
        """Validate the complete configuration."""
        if self.wallet_selection == "first_n" and (self.wallet_count is None or self.wallet_count < 1):
            raise ValueError("wallet_selection 'first_n' requires positive wallet_count")
        
        if self.wallet_selection == "random" and (self.wallet_count is None or self.wallet_count < 1):
            raise ValueError("wallet_selection 'random' requires positive wallet_count")
        
        if self.wallet_selection == "custom" and not self.custom_wallet_indices:
            raise ValueError("wallet_selection 'custom' requires custom_wallet_indices")
        
        if self.balance_check_threshold < 0:
            raise ValueError("balance_check_threshold must be non-negative")


class ConfigurationManager:
    """Manages configuration loading, validation, and saving."""
    
    def __init__(self, config_dir: str = "data/configs"):
        """Initialize configuration manager."""
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def load_config(self, config_path: str) -> SwapConfiguration:
        """Load configuration from file."""
        config_file = Path(config_path)
        
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        try:
            with open(config_file, 'r') as f:
                config_data = json.load(f)
            
            # Convert string enums to enum instances
            config_data['operation'] = OperationType(config_data['operation'])
            config_data['amount_config']['strategy'] = AmountStrategy(config_data['amount_config']['strategy'])
            config_data['execution_config']['mode'] = ExecutionMode(config_data['execution_config']['mode'])
            
            # Create configuration objects
            token_config = TokenConfig(**config_data['token_config'])
            amount_config = AmountConfig(**config_data['amount_config'])
            execution_config = ExecutionConfig(**config_data['execution_config'])
            
            # Remove nested configs from main data
            config_data['token_config'] = token_config
            config_data['amount_config'] = amount_config
            config_data['execution_config'] = execution_config
            
            return SwapConfiguration(**config_data)
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {str(e)}")
            raise ValueError(f"Invalid configuration file: {str(e)}")
    
    def save_config(self, config: SwapConfiguration, config_path: str) -> None:
        """Save configuration to file."""
        config_file = Path(config_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Validate configuration completeness before saving
            config.token_config.validate_complete()
            
            # Convert configuration to dictionary
            config_dict = self._config_to_dict(config)
            
            with open(config_file, 'w') as f:
                json.dump(config_dict, f, indent=2)
            
            logger.info(f"Configuration saved to: {config_path}")
            
        except Exception as e:
            logger.error(f"Failed to save configuration: {str(e)}")
            raise
    
    def _config_to_dict(self, config: SwapConfiguration) -> Dict[str, Any]:
        """Convert configuration object to dictionary."""
        return {
            "operation": config.operation.value,
            "token_config": {
                "input_token": config.token_config.input_token,
                "output_token": config.token_config.output_token,
                "input_mint": config.token_config.input_mint,
                "output_mint": config.token_config.output_mint
            },
            "amount_config": {
                "strategy": config.amount_config.strategy.value,
                "base_amount": config.amount_config.base_amount,
                "percentage": config.amount_config.percentage,
                "min_amount": config.amount_config.min_amount,
                "max_amount": config.amount_config.max_amount,
                "custom_amounts": config.amount_config.custom_amounts
            },
            "execution_config": {
                "mode": config.execution_config.mode.value,
                "max_concurrent": config.execution_config.max_concurrent,
                "batch_size": config.execution_config.batch_size,
                "delay_between_batches": config.execution_config.delay_between_batches,
                "delay_between_swaps": config.execution_config.delay_between_swaps,
                "slippage_bps": config.execution_config.slippage_bps,
                "verify_swaps": config.execution_config.verify_swaps,
                "collect_fees": config.execution_config.collect_fees,
                "retry_failed": config.execution_config.retry_failed,
                "max_retries": config.execution_config.max_retries
            },
            "mother_wallet_address": config.mother_wallet_address,
            "use_saved_wallets": config.use_saved_wallets,
            "wallet_selection": config.wallet_selection,
            "wallet_count": config.wallet_count,
            "custom_wallet_indices": config.custom_wallet_indices,
            "generate_report": config.generate_report,
            "report_format": config.report_format,
            "log_level": config.log_level,
            "save_results": config.save_results,
            "dry_run": config.dry_run,
            "confirm_before_execution": config.confirm_before_execution,
            "balance_check_threshold": config.balance_check_threshold
        }
    
    def create_template_config(self, operation: OperationType, output_path: str) -> SwapConfiguration:
        """Create a template configuration file."""
        if operation == OperationType.BUY:
            # Template for buying tokens with SOL
            template_config = SwapConfiguration(
                operation=OperationType.BUY,
                token_config=TokenConfig(
                    input_token="SOL",
                    output_token="USDC"
                ),
                amount_config=AmountConfig(
                    strategy=AmountStrategy.FIXED,
                    base_amount=0.1  # 0.1 SOL per wallet
                ),
                execution_config=ExecutionConfig(
                    mode=ExecutionMode.SEQUENTIAL,
                    slippage_bps=100,  # 1% slippage for safety
                    verify_swaps=True
                ),
                dry_run=True  # Safe default
            )
        else:
            # Template for selling tokens for SOL
            template_config = SwapConfiguration(
                operation=OperationType.SELL,
                token_config=TokenConfig(
                    input_token="USDC",
                    output_token="SOL"
                ),
                amount_config=AmountConfig(
                    strategy=AmountStrategy.PERCENTAGE,
                    percentage=0.5  # Sell 50% of token balance
                ),
                execution_config=ExecutionConfig(
                    mode=ExecutionMode.SEQUENTIAL,
                    slippage_bps=100,
                    verify_swaps=True
                ),
                dry_run=True
            )
        
        self.save_config(template_config, output_path)
        return template_config


# Predefined configuration templates
DEFAULT_BUY_CONFIG = {
    "operation": "buy",
    "token_config": {
        "input_token": "SOL",
        "output_token": "USDC"
    },
    "amount_config": {
        "strategy": "fixed",
        "base_amount": 0.1
    },
    "execution_config": {
        "mode": "sequential",
        "slippage_bps": 100,
        "verify_swaps": True,
        "max_concurrent": 3
    },
    "dry_run": True,
    "confirm_before_execution": True
}

DEFAULT_SELL_CONFIG = {
    "operation": "sell",
    "token_config": {
        "input_token": "USDC",
        "output_token": "SOL"
    },
    "amount_config": {
        "strategy": "percentage",
        "percentage": 0.5
    },
    "execution_config": {
        "mode": "sequential",
        "slippage_bps": 100,
        "verify_swaps": True,
        "max_concurrent": 3
    },
    "dry_run": True,
    "confirm_before_execution": True
}


def validate_token_pair(input_token: str, output_token: str) -> Dict[str, Any]:
    """
    Validate a token pair for swapping.
    
    Args:
        input_token: Input token symbol or mint address
        output_token: Output token symbol or mint address
    
    Returns:
        Validation result with resolved mint addresses if valid
    """
    # Common token symbol to mint address mapping
    KNOWN_TOKENS = {
        "SOL": "So11111111111111111111111111111111111111112",
        "WSOL": "So11111111111111111111111111111111111111112", 
        "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    }
    
    def resolve_token(token: str) -> Optional[str]:
        """Resolve token symbol to mint address."""
        if token in KNOWN_TOKENS:
            return KNOWN_TOKENS[token]
        elif len(token) >= 32:  # Likely a mint address
            return token
        return None
    
    input_mint = resolve_token(input_token)
    output_mint = resolve_token(output_token)
    
    if not input_mint:
        return {
            "valid": False,
            "error": f"Unsupported input token: {input_token}",
            "supported_tokens": list(KNOWN_TOKENS.keys())
        }
    
    if not output_mint:
        return {
            "valid": False,
            "error": f"Unsupported output token: {output_token}",
            "supported_tokens": list(KNOWN_TOKENS.keys())
        }
    
    if input_mint == output_mint:
        return {
            "valid": False,
            "error": "Input and output tokens cannot be the same"
        }
    
    return {
        "valid": True,
        "input_mint": input_mint,
        "output_mint": output_mint,
        "input_symbol": input_token,
        "output_symbol": output_token
    }


# Example configurations for testing
EXAMPLE_AMOUNT_CONFIGS = {
    "small_fixed": AmountConfig(
        strategy=AmountStrategy.FIXED,
        base_amount=0.01
    ),
    "medium_fixed": AmountConfig(
        strategy=AmountStrategy.FIXED,
        base_amount=0.1
    ),
    "conservative_percentage": AmountConfig(
        strategy=AmountStrategy.PERCENTAGE,
        percentage=0.1  # 10% of balance
    ),
    "aggressive_percentage": AmountConfig(
        strategy=AmountStrategy.PERCENTAGE,
        percentage=0.5  # 50% of balance
    ),
    "small_random": AmountConfig(
        strategy=AmountStrategy.RANDOM,
        min_amount=0.01,
        max_amount=0.05
    ),
    "medium_random": AmountConfig(
        strategy=AmountStrategy.RANDOM,
        min_amount=0.05,
        max_amount=0.2
    )
} 