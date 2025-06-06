"""
Amount calculation module for SPL Token Buy/Sell Script.
Handles different strategies for calculating swap amounts per wallet.
"""

import random
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from loguru import logger
from .buy_sell_config import AmountStrategy, AmountConfig


@dataclass
class WalletAmountResult:
    """Result of amount calculation for a specific wallet."""
    wallet_index: int
    wallet_address: str
    calculated_amount: float
    strategy_used: AmountStrategy
    source_balance: Optional[float] = None
    percentage_used: Optional[float] = None
    error: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if the amount calculation is valid."""
        return self.error is None and self.calculated_amount > 0


class AmountCalculator:
    """Calculates swap amounts for multiple wallets based on different strategies."""
    
    def __init__(self, api_client):
        """Initialize with API client for balance checking."""
        self.api_client = api_client
    
    def calculate_amounts(
        self,
        wallet_addresses: List[str],
        amount_config: AmountConfig,
        token_mint: str = "So11111111111111111111111111111111111111112",  # Default to SOL
        min_balance_threshold: float = 0.001
    ) -> List[WalletAmountResult]:
        """
        Calculate swap amounts for multiple wallets based on strategy.
        
        Args:
            wallet_addresses: List of wallet addresses
            amount_config: Amount calculation configuration
            token_mint: Token mint address for balance checking (SOL by default)
            min_balance_threshold: Minimum balance required after swap
        
        Returns:
            List of amount calculation results for each wallet
        """
        logger.info(f"Calculating amounts for {len(wallet_addresses)} wallets using {amount_config.strategy.value} strategy")
        
        results = []
        
        if amount_config.strategy == AmountStrategy.FIXED:
            results = self._calculate_fixed_amounts(wallet_addresses, amount_config)
        
        elif amount_config.strategy == AmountStrategy.PERCENTAGE:
            results = self._calculate_percentage_amounts(
                wallet_addresses, amount_config, token_mint, min_balance_threshold
            )
        
        elif amount_config.strategy == AmountStrategy.RANDOM:
            results = self._calculate_random_amounts(wallet_addresses, amount_config)
        
        elif amount_config.strategy == AmountStrategy.CUSTOM:
            results = self._calculate_custom_amounts(wallet_addresses, amount_config)
        
        else:
            # Fallback to fixed amounts
            logger.warning(f"Unknown strategy {amount_config.strategy}, falling back to fixed amounts")
            fixed_config = AmountConfig(strategy=AmountStrategy.FIXED, base_amount=0.01)
            results = self._calculate_fixed_amounts(wallet_addresses, fixed_config)
        
        # Log summary
        valid_results = [r for r in results if r.is_valid]
        total_amount = sum(r.calculated_amount for r in valid_results)
        
        logger.info(
            f"Amount calculation complete: {len(valid_results)}/{len(results)} valid, "
            f"total amount: {total_amount:.6f}"
        )
        
        return results
    
    def _calculate_fixed_amounts(
        self, 
        wallet_addresses: List[str], 
        amount_config: AmountConfig
    ) -> List[WalletAmountResult]:
        """Calculate fixed amounts for all wallets."""
        base_amount = amount_config.base_amount
        
        results = []
        for i, address in enumerate(wallet_addresses):
            results.append(WalletAmountResult(
                wallet_index=i,
                wallet_address=address,
                calculated_amount=base_amount,
                strategy_used=AmountStrategy.FIXED
            ))
        
        logger.debug(f"Fixed amount calculation: {base_amount} per wallet")
        return results
    
    def _calculate_percentage_amounts(
        self,
        wallet_addresses: List[str],
        amount_config: AmountConfig, 
        token_mint: str,
        min_balance_threshold: float
    ) -> List[WalletAmountResult]:
        """Calculate percentage-based amounts based on wallet balances."""
        percentage = amount_config.percentage
        results = []
        
        logger.debug(f"Calculating {percentage*100}% of balance for each wallet")
        
        for i, address in enumerate(wallet_addresses):
            try:
                # Get wallet balance
                balance_info = self.api_client.check_balance(address, token_mint)
                
                # Extract SOL balance (assuming SOL is the primary token for most operations)
                sol_balance = 0.0
                for balance in balance_info.get('balances', []):
                    if balance.get('symbol') == 'SOL':
                        sol_balance = balance.get('amount', 0.0)
                        break
                
                if sol_balance <= min_balance_threshold:
                    results.append(WalletAmountResult(
                        wallet_index=i,
                        wallet_address=address,
                        calculated_amount=0.0,
                        strategy_used=AmountStrategy.PERCENTAGE,
                        source_balance=sol_balance,
                        error=f"Insufficient balance: {sol_balance:.6f} SOL"
                    ))
                    continue
                
                # Calculate amount ensuring minimum balance remains
                available_balance = sol_balance - min_balance_threshold
                calculated_amount = available_balance * percentage
                
                # Ensure we don't exceed available balance
                if calculated_amount > available_balance:
                    calculated_amount = available_balance
                
                results.append(WalletAmountResult(
                    wallet_index=i,
                    wallet_address=address,
                    calculated_amount=calculated_amount,
                    strategy_used=AmountStrategy.PERCENTAGE,
                    source_balance=sol_balance,
                    percentage_used=percentage
                ))
                
            except Exception as e:
                logger.warning(f"Failed to get balance for wallet {address}: {str(e)}")
                results.append(WalletAmountResult(
                    wallet_index=i,
                    wallet_address=address,
                    calculated_amount=0.0,
                    strategy_used=AmountStrategy.PERCENTAGE,
                    error=f"Balance check failed: {str(e)}"
                ))
        
        return results
    
    def _calculate_random_amounts(
        self,
        wallet_addresses: List[str],
        amount_config: AmountConfig
    ) -> List[WalletAmountResult]:
        """Calculate random amounts within specified range for each wallet."""
        min_amount = amount_config.min_amount
        max_amount = amount_config.max_amount
        
        results = []
        
        logger.debug(f"Calculating random amounts between {min_amount} and {max_amount}")
        
        for i, address in enumerate(wallet_addresses):
            # Generate random amount within range
            calculated_amount = random.uniform(min_amount, max_amount)
            
            results.append(WalletAmountResult(
                wallet_index=i,
                wallet_address=address,
                calculated_amount=calculated_amount,
                strategy_used=AmountStrategy.RANDOM
            ))
        
        return results
    
    def _calculate_custom_amounts(
        self,
        wallet_addresses: List[str],
        amount_config: AmountConfig
    ) -> List[WalletAmountResult]:
        """Use custom amounts specified in configuration."""
        custom_amounts = amount_config.custom_amounts or []
        results = []
        
        logger.debug(f"Using custom amounts for {len(custom_amounts)} wallets")
        
        for i, address in enumerate(wallet_addresses):
            if i < len(custom_amounts):
                calculated_amount = custom_amounts[i]
            else:
                # If we run out of custom amounts, use the last one or zero
                calculated_amount = custom_amounts[-1] if custom_amounts else 0.0
                logger.warning(f"No custom amount for wallet {i}, using {calculated_amount}")
            
            results.append(WalletAmountResult(
                wallet_index=i,
                wallet_address=address,
                calculated_amount=calculated_amount,
                strategy_used=AmountStrategy.CUSTOM
            ))
        
        return results
    
    def validate_amounts(
        self,
        amount_results: List[WalletAmountResult],
        total_budget: Optional[float] = None,
        per_wallet_limit: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Validate calculated amounts against constraints.
        
        Args:
            amount_results: Results from amount calculation
            total_budget: Maximum total amount across all wallets
            per_wallet_limit: Maximum amount per individual wallet
        
        Returns:
            Validation result with details
        """
        valid_results = [r for r in amount_results if r.is_valid]
        invalid_results = [r for r in amount_results if not r.is_valid]
        
        total_amount = sum(r.calculated_amount for r in valid_results)
        max_wallet_amount = max((r.calculated_amount for r in valid_results), default=0.0)
        min_wallet_amount = min((r.calculated_amount for r in valid_results), default=0.0)
        
        issues = []
        
        # Check total budget constraint
        if total_budget and total_amount > total_budget:
            issues.append(f"Total amount {total_amount:.6f} exceeds budget {total_budget:.6f}")
        
        # Check per-wallet limit
        if per_wallet_limit and max_wallet_amount > per_wallet_limit:
            issues.append(f"Wallet amount {max_wallet_amount:.6f} exceeds limit {per_wallet_limit:.6f}")
        
        # Check for zero amounts
        zero_amount_wallets = len([r for r in valid_results if r.calculated_amount == 0])
        if zero_amount_wallets > 0:
            issues.append(f"{zero_amount_wallets} wallets have zero amounts")
        
        return {
            "valid": len(issues) == 0,
            "total_wallets": len(amount_results),
            "valid_wallets": len(valid_results),
            "invalid_wallets": len(invalid_results),
            "total_amount": total_amount,
            "average_amount": total_amount / len(valid_results) if valid_results else 0.0,
            "max_wallet_amount": max_wallet_amount,
            "min_wallet_amount": min_wallet_amount,
            "issues": issues,
            "invalid_wallet_errors": [r.error for r in invalid_results if r.error]
        }
    
    def adjust_amounts_for_budget(
        self,
        amount_results: List[WalletAmountResult],
        total_budget: float,
        adjustment_strategy: str = "proportional"
    ) -> List[WalletAmountResult]:
        """
        Adjust amounts to fit within total budget.
        
        Args:
            amount_results: Original amount calculation results
            total_budget: Maximum total budget
            adjustment_strategy: How to adjust amounts ("proportional", "equal_reduction")
        
        Returns:
            Adjusted amount results
        """
        valid_results = [r for r in amount_results if r.is_valid]
        invalid_results = [r for r in amount_results if not r.is_valid]
        
        if not valid_results:
            return amount_results
        
        current_total = sum(r.calculated_amount for r in valid_results)
        
        if current_total <= total_budget:
            return amount_results  # No adjustment needed
        
        logger.info(f"Adjusting amounts: current total {current_total:.6f} > budget {total_budget:.6f}")
        
        adjusted_results = []
        
        if adjustment_strategy == "proportional":
            # Scale all amounts proportionally
            scale_factor = total_budget / current_total
            
            for result in valid_results:
                adjusted_amount = result.calculated_amount * scale_factor
                adjusted_result = WalletAmountResult(
                    wallet_index=result.wallet_index,
                    wallet_address=result.wallet_address,
                    calculated_amount=adjusted_amount,
                    strategy_used=result.strategy_used,
                    source_balance=result.source_balance,
                    percentage_used=result.percentage_used
                )
                adjusted_results.append(adjusted_result)
        
        elif adjustment_strategy == "equal_reduction":
            # Reduce each amount by equal absolute amount
            reduction_per_wallet = (current_total - total_budget) / len(valid_results)
            
            for result in valid_results:
                adjusted_amount = max(0.0, result.calculated_amount - reduction_per_wallet)
                adjusted_result = WalletAmountResult(
                    wallet_index=result.wallet_index,
                    wallet_address=result.wallet_address,
                    calculated_amount=adjusted_amount,
                    strategy_used=result.strategy_used,
                    source_balance=result.source_balance,
                    percentage_used=result.percentage_used
                )
                adjusted_results.append(adjusted_result)
        
        # Add back invalid results unchanged
        adjusted_results.extend(invalid_results)
        
        # Sort by wallet index to maintain order
        adjusted_results.sort(key=lambda x: x.wallet_index)
        
        new_total = sum(r.calculated_amount for r in adjusted_results if r.is_valid)
        logger.info(f"Amount adjustment complete: new total {new_total:.6f}")
        
        return adjusted_results


def calculate_amounts_simple(
    wallet_count: int,
    strategy: str,
    **kwargs
) -> List[float]:
    """
    Simple amount calculation function for testing and quick scripts.
    
    Args:
        wallet_count: Number of wallets
        strategy: Strategy name ("fixed", "random", "percentage")
        **kwargs: Strategy-specific parameters
    
    Returns:
        List of calculated amounts
    
    Examples:
        calculate_amounts_simple(3, "fixed", amount=0.1) → [0.1, 0.1, 0.1]
        calculate_amounts_simple(3, "random", min=0.05, max=0.2) → [0.087, 0.156, 0.093]
    """
    if strategy == "fixed":
        amount = kwargs.get("amount", 0.1)
        return [amount] * wallet_count
    
    elif strategy == "random":
        min_amount = kwargs.get("min", 0.01)
        max_amount = kwargs.get("max", 0.1)
        return [random.uniform(min_amount, max_amount) for _ in range(wallet_count)]
    
    elif strategy == "percentage":
        # For simple calculation, assume fixed balance and percentage
        balance = kwargs.get("balance", 1.0)
        percentage = kwargs.get("percentage", 0.1)
        amount = balance * percentage
        return [amount] * wallet_count
    
    else:
        raise ValueError(f"Unknown strategy: {strategy}")


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