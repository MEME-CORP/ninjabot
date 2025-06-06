#!/usr/bin/env python3
"""
SPL Token Buy/Sell Script
A comprehensive script for buying and selling SPL tokens across multiple wallets using Jupiter DEX.

Usage:
    python spl_buy_sell_script.py --config config.json
    python spl_buy_sell_script.py --operation buy --input-token SOL --output-token USDC --amount 0.1 --wallets 5
    python spl_buy_sell_script.py --template buy --output buy_config.json
"""

import argparse
import asyncio
import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add the bot directory to Python path for imports
sys.path.append(str(Path(__file__).parent.parent))

from loguru import logger
from api.api_client import api_client, ApiClientError
from scripts.buy_sell_config import (
    SwapConfiguration, ConfigurationManager, OperationType, TokenConfig,
    AmountConfig, AmountStrategy, ExecutionConfig, ExecutionMode,
    validate_token_pair, DEFAULT_BUY_CONFIG, DEFAULT_SELL_CONFIG
)
from scripts.wallet_swap_manager import WalletSwapManager, ExecutionSummary
from scripts.result_reporter import ResultReporter, create_quick_report, save_execution_results


class SPLBuySellScript:
    """Main script class for SPL token buy/sell operations."""
    
    def __init__(self, use_mock: bool = False):
        """Initialize the script."""
        self.use_mock = use_mock
        self.config_manager = ConfigurationManager()
        self.result_reporter = ResultReporter()
        self.swap_manager = WalletSwapManager(api_client, use_mock=use_mock)
        
        # Set up progress callback
        self.swap_manager.set_progress_callback(self._progress_callback)
        
        # Configure logging
        logger.remove()  # Remove default handler
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level="INFO"
        )
        logger.add(
            "logs/spl_buy_sell_{time}.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG",
            rotation="1 day",
            retention="7 days"
        )
    
    def _progress_callback(self, stage: str, current: int, total: int) -> None:
        """Handle progress updates."""
        if total > 0:
            percentage = (current / total) * 100
            print(f"\r{stage}: {current}/{total} ({percentage:.1f}%)", end="", flush=True)
            if current == total:
                print()  # New line when complete
    
    async def run_from_config(self, config_path: str) -> ExecutionSummary:
        """Run the script using a configuration file."""
        logger.info(f"Loading configuration from: {config_path}")
        
        try:
            config = self.config_manager.load_config(config_path)
        except Exception as e:
            logger.error(f"Failed to load configuration: {str(e)}")
            raise
        
        return await self.run_with_config(config)
    
    async def run_with_config(self, config: SwapConfiguration) -> ExecutionSummary:
        """Run the script with a SwapConfiguration object."""
        logger.info(f"Starting {config.operation.value} operation: {config.token_config.input_token} → {config.token_config.output_token}")
        
        # Validate configuration
        validation_errors = self._validate_config(config)
        if validation_errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(validation_errors)}")
        
        # Load wallet data
        wallet_data = await self._load_wallet_data(config)
        if not wallet_data:
            raise ValueError("No wallet data available")
        
        logger.info(f"Loaded {len(wallet_data)} wallets")
        
        # Show confirmation if required
        if config.confirm_before_execution and not config.dry_run:
            if not await self._confirm_execution(config, wallet_data):
                logger.info("Execution cancelled by user")
                raise KeyboardInterrupt("Execution cancelled")
        
        # Execute swaps
        try:
            summary = await self.swap_manager.execute_swaps(config, wallet_data)
            
            # Generate and display report
            console_report = create_quick_report(summary)
            print("\n" + console_report)
            
            # Save detailed report if requested
            if config.save_results:
                report_path = save_execution_results(summary, config.report_format)
                logger.info(f"Detailed report saved: {report_path}")
            
            return summary
            
        except KeyboardInterrupt:
            logger.info("Execution interrupted by user")
            self.swap_manager.cancel_execution()
            raise
        except Exception as e:
            logger.error(f"Execution failed: {str(e)}")
            raise
    
    async def run_quick(
        self,
        operation: str,
        input_token: str,
        output_token: str,
        amount: float,
        wallet_count: Optional[int] = None,
        execution_mode: str = "sequential"
    ) -> ExecutionSummary:
        """Run a quick swap with minimal configuration."""
        logger.info(f"Quick {operation}: {amount} {input_token} → {output_token}")
        
        # Validate token pair
        token_validation = validate_token_pair(input_token, output_token)
        if not token_validation["valid"]:
            raise ValueError(f"Invalid token pair: {token_validation['error']}")
        
        # Create configuration
        config = SwapConfiguration(
            operation=OperationType.BUY if operation.lower() == "buy" else OperationType.SELL,
            token_config=TokenConfig(
                input_token=input_token,
                output_token=output_token,
                input_mint=token_validation["input_mint"],
                output_mint=token_validation["output_mint"]
            ),
            amount_config=AmountConfig(
                strategy=AmountStrategy.FIXED,
                base_amount=amount
            ),
            execution_config=ExecutionConfig(
                mode=ExecutionMode(execution_mode.lower()),
                verify_swaps=True,
                collect_fees=True
            ),
            wallet_count=wallet_count,
            confirm_before_execution=False,
            dry_run=self.use_mock
        )
        
        return await self.run_with_config(config)
    
    def create_template(self, operation: str, output_path: str) -> None:
        """Create a template configuration file."""
        logger.info(f"Creating {operation} template: {output_path}")
        
        operation_type = OperationType.BUY if operation.lower() == "buy" else OperationType.SELL
        self.config_manager.create_template_config(operation_type, output_path)
        
        print(f"Template configuration created: {output_path}")
        print("Edit the configuration file and run with: --config " + output_path)
    
    def _validate_config(self, config: SwapConfiguration) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        # Validate token pair
        token_validation = validate_token_pair(
            config.token_config.input_token,
            config.token_config.output_token
        )
        if not token_validation["valid"]:
            errors.append(f"Invalid token pair: {token_validation['error']}")
        else:
            # Update config with resolved mint addresses
            config.token_config.input_mint = token_validation["input_mint"]
            config.token_config.output_mint = token_validation["output_mint"]
        
        # Validate amount strategy parameters
        if config.amount_config.strategy == AmountStrategy.FIXED:
            if config.amount_config.base_amount is None or config.amount_config.base_amount <= 0:
                errors.append("Fixed amount strategy requires positive base_amount")
        
        elif config.amount_config.strategy == AmountStrategy.PERCENTAGE:
            if config.amount_config.percentage is None or not (0.0 < config.amount_config.percentage <= 1.0):
                errors.append("Percentage strategy requires percentage between 0.0 and 1.0")
        
        elif config.amount_config.strategy == AmountStrategy.RANDOM:
            if (config.amount_config.min_amount is None or config.amount_config.max_amount is None or
                config.amount_config.min_amount >= config.amount_config.max_amount):
                errors.append("Random strategy requires valid min_amount < max_amount")
        
        # Validate execution parameters
        if config.execution_config.slippage_bps < 0 or config.execution_config.slippage_bps > 5000:
            errors.append("Slippage tolerance should be between 0 and 5000 basis points (50%)")
        
        return errors
    
    async def _load_wallet_data(self, config: SwapConfiguration) -> List[Dict[str, Any]]:
        """Load wallet data based on configuration."""
        if config.use_saved_wallets:
            # Load from saved wallets
            if config.mother_wallet_address:
                # Load child wallets for specific mother wallet
                child_wallets = api_client.load_child_wallets(config.mother_wallet_address)
                if child_wallets:
                    logger.info(f"Loaded {len(child_wallets)} child wallets for mother: {config.mother_wallet_address}")
                    return child_wallets
            else:
                # Try to find any saved mother wallets
                saved_mothers = api_client.list_saved_wallets('mother')
                if saved_mothers:
                    # Use the first saved mother wallet
                    mother_address = saved_mothers[0]['address']
                    child_wallets = api_client.load_child_wallets(mother_address)
                    if child_wallets:
                        logger.info(f"Using first saved mother wallet: {mother_address}")
                        return child_wallets
        
        # Fallback: create mock wallet data for testing
        if self.use_mock:
            logger.warning("No saved wallets found, creating mock wallet data")
            mock_count = config.wallet_count or 5
            return [
                {
                    "address": f"mock_wallet_{i}_{''.join(f'{j:02x}' for j in range(16))}",
                    "private_key": f"mock_private_key_{i}_{''.join(f'{j:02x}' for j in range(32))}"
                }
                for i in range(mock_count)
            ]
        
        raise ValueError("No wallet data available. Please create wallets first or enable mock mode.")
    
    async def _confirm_execution(self, config: SwapConfiguration, wallet_data: List[Dict[str, Any]]) -> bool:
        """Show execution details and ask for confirmation."""
        print("\n" + "="*60)
        print("EXECUTION CONFIRMATION")
        print("="*60)
        print(f"Operation: {config.operation.value.upper()}")
        print(f"Token Pair: {config.token_config.input_token} → {config.token_config.output_token}")
        print(f"Wallets: {len(wallet_data)}")
        print(f"Amount Strategy: {config.amount_config.strategy.value}")
        
        if config.amount_config.strategy == AmountStrategy.FIXED:
            total_amount = config.amount_config.base_amount * len(wallet_data)
            print(f"Amount per wallet: {config.amount_config.base_amount}")
            print(f"Total amount: {total_amount}")
        elif config.amount_config.strategy == AmountStrategy.PERCENTAGE:
            print(f"Percentage: {config.amount_config.percentage * 100:.1f}% of balance")
        elif config.amount_config.strategy == AmountStrategy.RANDOM:
            print(f"Random range: {config.amount_config.min_amount} - {config.amount_config.max_amount}")
        
        print(f"Execution Mode: {config.execution_config.mode.value}")
        print(f"Slippage Tolerance: {config.execution_config.slippage_bps / 100:.2f}%")
        print(f"Fee Collection: {'Enabled' if config.execution_config.collect_fees else 'Disabled'}")
        print(f"Verification: {'Enabled' if config.execution_config.verify_swaps else 'Disabled'}")
        print("="*60)
        
        response = input("Proceed with execution? (y/N): ").strip().lower()
        return response in ['y', 'yes']


def create_cli_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description="SPL Token Buy/Sell Script - Execute token swaps across multiple wallets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use configuration file
  python spl_buy_sell_script.py --config buy_config.json
  
  # Quick buy with minimal setup
  python spl_buy_sell_script.py --operation buy --input-token SOL --output-token USDC --amount 0.1
  
  # Create template configuration
  python spl_buy_sell_script.py --template buy --output buy_template.json
  
  # Mock execution for testing
  python spl_buy_sell_script.py --mock --operation sell --input-token USDC --output-token SOL --amount 10
        """
    )
    
    # Main operation modes
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--config", type=str, help="Path to configuration file")
    mode_group.add_argument("--template", choices=["buy", "sell"], help="Create template configuration")
    mode_group.add_argument("--operation", choices=["buy", "sell"], help="Quick operation mode")
    
    # Template output
    parser.add_argument("--output", type=str, help="Output path for template (required with --template)")
    
    # Quick operation parameters
    parser.add_argument("--input-token", type=str, help="Input token symbol or mint address")
    parser.add_argument("--output-token", type=str, help="Output token symbol or mint address")
    parser.add_argument("--amount", type=float, help="Amount per wallet (for quick mode)")
    parser.add_argument("--wallets", type=int, help="Number of wallets to use (0 = all)")
    parser.add_argument("--mode", choices=["sequential", "parallel", "batch"], 
                       default="sequential", help="Execution mode")
    
    # Global options
    parser.add_argument("--mock", action="store_true", help="Use mock mode (no real transactions)")
    parser.add_argument("--no-confirm", action="store_true", help="Skip execution confirmation")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], 
                       default="INFO", help="Logging level")
    parser.add_argument("--report-format", choices=["json", "csv", "yaml"], 
                       default="json", help="Report output format")
    
    return parser


async def main():
    """Main script entry point."""
    parser = create_cli_parser()
    args = parser.parse_args()
    
    # Validate argument combinations
    if args.template and not args.output:
        parser.error("--template requires --output")
    
    if args.operation and not all([args.input_token, args.output_token, args.amount]):
        parser.error("--operation requires --input-token, --output-token, and --amount")
    
    # Initialize script
    script = SPLBuySellScript(use_mock=args.mock)
    
    # Configure logging level
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=args.log_level
    )
    
    try:
        if args.template:
            # Create template
            script.create_template(args.template, args.output)
            
        elif args.config:
            # Run from configuration file
            summary = await script.run_from_config(args.config)
            
            # Print final summary
            print(f"\nExecution completed: {summary.total_success_count}/{len(summary.all_swap_results)} successful")
            if summary.total_failure_count > 0:
                print(f"Failed swaps: {summary.total_failure_count}")
            
        elif args.operation:
            # Quick operation mode
            wallet_count = args.wallets if args.wallets and args.wallets > 0 else None
            
            summary = await script.run_quick(
                operation=args.operation,
                input_token=args.input_token,
                output_token=args.output_token,
                amount=args.amount,
                wallet_count=wallet_count,
                execution_mode=args.mode
            )
            
            print(f"\nQuick {args.operation} completed: {summary.total_success_count}/{len(summary.all_swap_results)} successful")
        
        return 0
        
    except KeyboardInterrupt:
        print("\nExecution interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Script failed: {str(e)}")
        if args.log_level == "DEBUG":
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    # Handle Windows event loop policy
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 