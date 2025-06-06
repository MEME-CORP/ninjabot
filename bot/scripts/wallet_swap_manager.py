"""
Wallet swap manager for SPL Token Buy/Sell Script.
Orchestrates multi-wallet swap execution with different execution modes.
"""

import asyncio
import time
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

from loguru import logger
from .buy_sell_config import SwapConfiguration, ExecutionMode
from .amount_calculator import AmountCalculator, WalletAmountResult
from .swap_executor import SwapExecutor, SwapResult, SwapStatus, MockSwapExecutor


@dataclass
class BatchExecutionResult:
    """Result of a batch execution."""
    batch_id: str
    start_time: float
    end_time: Optional[float] = None
    swap_results: List[SwapResult] = field(default_factory=list)
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate batch execution duration."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None
    
    @property
    def success_count(self) -> int:
        """Count successful swaps."""
        return len([r for r in self.swap_results if r.is_successful])
    
    @property
    def failure_count(self) -> int:
        """Count failed swaps.""" 
        return len([r for r in self.swap_results if not r.is_successful])
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        total = len(self.swap_results)
        if total == 0:
            return 0.0
        return (self.success_count / total) * 100


@dataclass
class ExecutionSummary:
    """Summary of complete execution across all batches."""
    config: SwapConfiguration
    start_time: float
    end_time: Optional[float] = None
    
    # Wallet and amount data
    total_wallets: int = 0
    selected_wallets: int = 0
    amount_calculation_results: List[WalletAmountResult] = field(default_factory=list)
    
    # Execution results
    batch_results: List[BatchExecutionResult] = field(default_factory=list)
    all_swap_results: List[SwapResult] = field(default_factory=list)
    
    # Status tracking
    execution_status: str = "pending"  # pending, in_progress, completed, failed
    error_message: Optional[str] = None
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate total execution duration."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None
    
    @property
    def total_success_count(self) -> int:
        """Total successful swaps across all batches."""
        return sum(batch.success_count for batch in self.batch_results)
    
    @property
    def total_failure_count(self) -> int:
        """Total failed swaps across all batches."""
        return sum(batch.failure_count for batch in self.batch_results)
    
    @property
    def overall_success_rate(self) -> float:
        """Overall success rate percentage."""
        total_swaps = len(self.all_swap_results)
        if total_swaps == 0:
            return 0.0
        return (self.total_success_count / total_swaps) * 100
    
    @property
    def total_volume_in(self) -> float:
        """Total input volume across successful swaps."""
        return sum(
            r.actual_input_amount or 0.0 
            for r in self.all_swap_results 
            if r.is_successful and r.actual_input_amount
        )
    
    @property
    def total_volume_out(self) -> float:
        """Total output volume across successful swaps."""
        return sum(
            r.actual_output_amount or 0.0 
            for r in self.all_swap_results 
            if r.is_successful and r.actual_output_amount
        )
    
    @property
    def average_price_impact(self) -> Optional[float]:
        """Average price impact across successful swaps."""
        impacts = [
            r.price_impact for r in self.all_swap_results 
            if r.is_successful and r.price_impact is not None
        ]
        return sum(impacts) / len(impacts) if impacts else None
    
    @property
    def total_fees_collected(self) -> float:
        """Total fees collected across all swaps."""
        return sum(
            r.fee_collected or 0.0 
            for r in self.all_swap_results 
            if r.fee_collected
        )


class WalletSwapManager:
    """Manages multi-wallet swap execution with different strategies."""
    
    def __init__(self, api_client, use_mock: bool = False):
        """Initialize the wallet swap manager."""
        self.api_client = api_client
        self.use_mock = use_mock
        self.amount_calculator = AmountCalculator(api_client)
        
        # Progress tracking
        self.progress_callback: Optional[Callable[[str, int, int], None]] = None
        self.is_cancelled = False
    
    def set_progress_callback(self, callback: Callable[[str, int, int], None]) -> None:
        """Set callback for progress updates."""
        self.progress_callback = callback
    
    def cancel_execution(self) -> None:
        """Cancel ongoing execution."""
        self.is_cancelled = True
        logger.info("Execution cancellation requested")
    
    async def execute_swaps(
        self, 
        config: SwapConfiguration,
        child_wallets_data: List[Dict[str, Any]]
    ) -> ExecutionSummary:
        """
        Execute swaps across multiple wallets according to configuration.
        
        Args:
            config: Swap configuration
            child_wallets_data: List of child wallet data with addresses and private keys
        
        Returns:
            Complete execution summary
        """
        summary = ExecutionSummary(
            config=config,
            start_time=time.time(),
            total_wallets=len(child_wallets_data),
            execution_status="in_progress"
        )
        
        logger.info(f"Starting swap execution: {config.operation.value} {config.token_config.input_token} → {config.token_config.output_token}")
        
        try:
            # Step 1: Select and prepare wallets
            selected_wallets = self._select_wallets(child_wallets_data, config)
            summary.selected_wallets = len(selected_wallets)
            
            if not selected_wallets:
                raise ValueError("No wallets selected for execution")
            
            logger.info(f"Selected {len(selected_wallets)} wallets for execution")
            
            # Step 2: Calculate amounts for each wallet
            self._report_progress("Calculating amounts", 0, len(selected_wallets))
            
            wallet_addresses = [w['address'] for w in selected_wallets]
            amount_results = self.amount_calculator.calculate_amounts(
                wallet_addresses=wallet_addresses,
                amount_config=config.amount_config,
                token_mint=config.token_config.input_mint or "So11111111111111111111111111111111111111112",
                min_balance_threshold=config.balance_check_threshold
            )
            
            summary.amount_calculation_results = amount_results
            
            # Validate amounts
            validation = self.amount_calculator.validate_amounts(amount_results)
            if not validation["valid"]:
                logger.warning(f"Amount validation issues: {validation['issues']}")
            
            # Step 3: Prepare swap tasks
            valid_amount_results = [r for r in amount_results if r.is_valid and r.calculated_amount > 0]
            
            if not valid_amount_results:
                raise ValueError("No valid amounts calculated for any wallet")
            
            logger.info(f"Prepared {len(valid_amount_results)} swaps with total volume: {sum(r.calculated_amount for r in valid_amount_results):.6f}")
            
            # Step 4: Execute swaps based on mode
            if config.execution_config.mode == ExecutionMode.SEQUENTIAL:
                await self._execute_sequential(config, selected_wallets, valid_amount_results, summary)
            elif config.execution_config.mode == ExecutionMode.PARALLEL:
                await self._execute_parallel(config, selected_wallets, valid_amount_results, summary)
            elif config.execution_config.mode == ExecutionMode.BATCH:
                await self._execute_batch(config, selected_wallets, valid_amount_results, summary)
            else:
                raise ValueError(f"Unknown execution mode: {config.execution_config.mode}")
            
            # Step 5: Finalize summary
            summary.execution_status = "completed"
            summary.end_time = time.time()
            
            logger.info(
                f"Execution completed: {summary.total_success_count}/{len(summary.all_swap_results)} successful "
                f"({summary.overall_success_rate:.1f}%) in {summary.duration:.2f}s"
            )
            
        except Exception as e:
            summary.execution_status = "failed"
            summary.error_message = str(e)
            summary.end_time = time.time()
            logger.error(f"Execution failed: {str(e)}")
            raise
        
        return summary
    
    def _select_wallets(
        self, 
        child_wallets_data: List[Dict[str, Any]], 
        config: SwapConfiguration
    ) -> List[Dict[str, Any]]:
        """Select wallets based on configuration."""
        if config.wallet_selection == "all":
            return child_wallets_data
        
        elif config.wallet_selection == "first_n":
            n = config.wallet_count or len(child_wallets_data)
            return child_wallets_data[:n]
        
        elif config.wallet_selection == "random":
            import random
            n = config.wallet_count or len(child_wallets_data)
            return random.sample(child_wallets_data, min(n, len(child_wallets_data)))
        
        elif config.wallet_selection == "custom":
            indices = config.custom_wallet_indices or []
            return [child_wallets_data[i] for i in indices if 0 <= i < len(child_wallets_data)]
        
        else:
            logger.warning(f"Unknown wallet selection: {config.wallet_selection}, using all")
            return child_wallets_data
    
    async def _execute_sequential(
        self,
        config: SwapConfiguration,
        selected_wallets: List[Dict[str, Any]],
        amount_results: List[WalletAmountResult],
        summary: ExecutionSummary
    ) -> None:
        """Execute swaps sequentially one by one."""
        logger.info("Executing swaps sequentially")
        
        # Create executor
        executor = self._create_executor(config.execution_config)
        
        # Create single batch
        batch = BatchExecutionResult(
            batch_id="sequential_batch",
            start_time=time.time()
        )
        
        # Execute each swap
        for i, amount_result in enumerate(amount_results):
            if self.is_cancelled:
                logger.info("Execution cancelled by user")
                break
            
            self._report_progress("Executing sequential swaps", i, len(amount_results))
            
            # Find corresponding wallet data
            wallet_data = next(
                (w for w in selected_wallets if w['address'] == amount_result.wallet_address),
                None
            )
            
            if not wallet_data:
                logger.warning(f"Wallet data not found for {amount_result.wallet_address}")
                continue
            
            # Execute swap
            swap_result = await executor.execute_swap(
                wallet_address=wallet_data['address'],
                wallet_private_key=wallet_data['private_key'],
                wallet_index=amount_result.wallet_index,
                input_token=config.token_config.input_token,
                output_token=config.token_config.output_token,
                amount=amount_result.calculated_amount
            )
            
            batch.swap_results.append(swap_result)
            summary.all_swap_results.append(swap_result)
            
            # Add delay between swaps
            if i < len(amount_results) - 1:  # Don't delay after last swap
                await asyncio.sleep(config.execution_config.delay_between_swaps)
        
        batch.end_time = time.time()
        summary.batch_results.append(batch)
    
    async def _execute_parallel(
        self,
        config: SwapConfiguration,
        selected_wallets: List[Dict[str, Any]],
        amount_results: List[WalletAmountResult],
        summary: ExecutionSummary
    ) -> None:
        """Execute swaps in parallel with concurrency limit."""
        logger.info(f"Executing swaps in parallel (max concurrent: {config.execution_config.max_concurrent})")
        
        # Create executor
        executor = self._create_executor(config.execution_config)
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(config.execution_config.max_concurrent)
        
        # Create single batch
        batch = BatchExecutionResult(
            batch_id="parallel_batch",
            start_time=time.time()
        )
        
        async def execute_single_swap(amount_result: WalletAmountResult) -> SwapResult:
            """Execute a single swap with semaphore control."""
            async with semaphore:
                if self.is_cancelled:
                    # Create cancelled result
                    return SwapResult(
                        wallet_address=amount_result.wallet_address,
                        wallet_index=amount_result.wallet_index,
                        wallet_private_key="",
                        input_token=config.token_config.input_token,
                        output_token=config.token_config.output_token,
                        input_amount=amount_result.calculated_amount,
                        status=SwapStatus.SKIPPED,
                        final_error="Execution cancelled"
                    )
                
                # Find wallet data
                wallet_data = next(
                    (w for w in selected_wallets if w['address'] == amount_result.wallet_address),
                    None
                )
                
                if not wallet_data:
                    return SwapResult(
                        wallet_address=amount_result.wallet_address,
                        wallet_index=amount_result.wallet_index,
                        wallet_private_key="",
                        input_token=config.token_config.input_token,
                        output_token=config.token_config.output_token,
                        input_amount=amount_result.calculated_amount,
                        status=SwapStatus.FAILED,
                        final_error="Wallet data not found"
                    )
                
                return await executor.execute_swap(
                    wallet_address=wallet_data['address'],
                    wallet_private_key=wallet_data['private_key'],
                    wallet_index=amount_result.wallet_index,
                    input_token=config.token_config.input_token,
                    output_token=config.token_config.output_token,
                    amount=amount_result.calculated_amount
                )
        
        # Create tasks for all swaps
        tasks = [execute_single_swap(amount_result) for amount_result in amount_results]
        
        # Execute with progress tracking
        completed = 0
        for task in asyncio.as_completed(tasks):
            swap_result = await task
            batch.swap_results.append(swap_result)
            summary.all_swap_results.append(swap_result)
            
            completed += 1
            self._report_progress("Executing parallel swaps", completed, len(tasks))
        
        batch.end_time = time.time()
        summary.batch_results.append(batch)
    
    async def _execute_batch(
        self,
        config: SwapConfiguration,
        selected_wallets: List[Dict[str, Any]],
        amount_results: List[WalletAmountResult],
        summary: ExecutionSummary
    ) -> None:
        """Execute swaps in batches with delays between batches."""
        batch_size = config.execution_config.batch_size
        logger.info(f"Executing swaps in batches of {batch_size}")
        
        # Create executor
        executor = self._create_executor(config.execution_config)
        
        # Split into batches
        batches = [amount_results[i:i + batch_size] for i in range(0, len(amount_results), batch_size)]
        
        for batch_num, batch_amount_results in enumerate(batches):
            if self.is_cancelled:
                logger.info("Execution cancelled by user")
                break
            
            batch = BatchExecutionResult(
                batch_id=f"batch_{batch_num + 1}",
                start_time=time.time()
            )
            
            logger.info(f"Executing batch {batch_num + 1}/{len(batches)} ({len(batch_amount_results)} swaps)")
            
            # Execute batch sequentially within batch
            for i, amount_result in enumerate(batch_amount_results):
                if self.is_cancelled:
                    break
                
                self._report_progress(
                    f"Executing batch {batch_num + 1}/{len(batches)}", 
                    i, 
                    len(batch_amount_results)
                )
                
                # Find wallet data
                wallet_data = next(
                    (w for w in selected_wallets if w['address'] == amount_result.wallet_address),
                    None
                )
                
                if not wallet_data:
                    logger.warning(f"Wallet data not found for {amount_result.wallet_address}")
                    continue
                
                # Execute swap
                swap_result = await executor.execute_swap(
                    wallet_address=wallet_data['address'],
                    wallet_private_key=wallet_data['private_key'],
                    wallet_index=amount_result.wallet_index,
                    input_token=config.token_config.input_token,
                    output_token=config.token_config.output_token,
                    amount=amount_result.calculated_amount
                )
                
                batch.swap_results.append(swap_result)
                summary.all_swap_results.append(swap_result)
                
                # Small delay between swaps within batch
                if i < len(batch_amount_results) - 1:
                    await asyncio.sleep(config.execution_config.delay_between_swaps)
            
            batch.end_time = time.time()
            summary.batch_results.append(batch)
            
            # Delay between batches (except after last batch)
            if batch_num < len(batches) - 1:
                logger.info(f"Waiting {config.execution_config.delay_between_batches}s before next batch")
                await asyncio.sleep(config.execution_config.delay_between_batches)
    
    def _create_executor(self, execution_config) -> SwapExecutor:
        """Create appropriate executor based on configuration."""
        if self.use_mock:
            return MockSwapExecutor(execution_config)
        else:
            return SwapExecutor(self.api_client, execution_config)
    
    def _report_progress(self, stage: str, current: int, total: int) -> None:
        """Report progress to callback if set."""
        if self.progress_callback:
            self.progress_callback(stage, current, total)
        
        # Also log progress
        if total > 0:
            percentage = (current / total) * 100
            logger.debug(f"{stage}: {current}/{total} ({percentage:.1f}%)")


# Helper functions for creating common configurations
def create_buy_manager(api_client, use_mock: bool = False) -> WalletSwapManager:
    """Create a wallet swap manager configured for buying tokens."""
    return WalletSwapManager(api_client, use_mock=use_mock)


def create_sell_manager(api_client, use_mock: bool = False) -> WalletSwapManager:
    """Create a wallet swap manager configured for selling tokens."""
    return WalletSwapManager(api_client, use_mock=use_mock)


async def execute_quick_swap(
    api_client,
    operation: str,  # "buy" or "sell"
    input_token: str,
    output_token: str,
    wallet_data: List[Dict[str, Any]],
    amount_per_wallet: float,
    use_mock: bool = False
) -> ExecutionSummary:
    """
    Quick swap execution for simple use cases.
    
    Args:
        api_client: API client instance
        operation: "buy" or "sell"
        input_token: Input token symbol or mint
        output_token: Output token symbol or mint
        wallet_data: List of wallet data with addresses and private keys
        amount_per_wallet: Fixed amount per wallet
        use_mock: Whether to use mock execution
    
    Returns:
        Execution summary
    """
    from .buy_sell_config import (
        SwapConfiguration, OperationType, TokenConfig, AmountConfig, 
        AmountStrategy, ExecutionConfig, ExecutionMode
    )
    
    # Create simple configuration
    config = SwapConfiguration(
        operation=OperationType.BUY if operation.lower() == "buy" else OperationType.SELL,
        token_config=TokenConfig(
            input_token=input_token,
            output_token=output_token
        ),
        amount_config=AmountConfig(
            strategy=AmountStrategy.FIXED,
            base_amount=amount_per_wallet
        ),
        execution_config=ExecutionConfig(
            mode=ExecutionMode.SEQUENTIAL,
            verify_swaps=True
        ),
        dry_run=use_mock,
        confirm_before_execution=False
    )
    
    # Execute swaps
    manager = WalletSwapManager(api_client, use_mock=use_mock)
    return await manager.execute_swaps(config, wallet_data) 