import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable
from loguru import logger

from bot.api.api_client import api_client
from bot.config import BALANCE_POLL_INTERVAL
from bot.events.event_system import event_system, BalanceChangeEvent

class BalancePoller:
    """
    Polls wallet balance at regular intervals.
    
    This class manages periodic checking of wallet balances and notifies
    when the balance changes or reaches a target value.
    """
    
    def __init__(self):
        """Initialize the balance poller."""
        self._polling_tasks: Dict[str, asyncio.Task] = {}
        self._last_balances: Dict[str, float] = {}
    
    async def start_polling(
        self,
        wallet_address: str,
        token_address: str,
        target_balance: Optional[float] = None,
        on_target_reached: Optional[Callable[[], Awaitable[None]]] = None,
        interval: int = BALANCE_POLL_INTERVAL
    ) -> str:
        """
        Start polling a wallet's balance.
        
        Args:
            wallet_address: Wallet address to poll
            token_address: Token contract address
            target_balance: Optional target balance to wait for
            on_target_reached: Callback to call when target reached
            interval: Polling interval in seconds
            
        Returns:
            Polling task ID
        """
        task_id = f"{wallet_address}_{token_address}"
        
        if task_id in self._polling_tasks:
            logger.warning(f"Already polling balance for {task_id}")
            return task_id
        
        # Create and start the polling task
        self._polling_tasks[task_id] = asyncio.create_task(
            self._poll_balance(
                wallet_address, 
                token_address, 
                target_balance, 
                on_target_reached,
                interval
            )
        )
        
        logger.info(
            f"Started balance polling for {wallet_address}",
            extra={
                "wallet": wallet_address,
                "token": token_address,
                "target_balance": target_balance,
                "interval": interval
            }
        )
        
        return task_id
    
    async def stop_polling(self, task_id: str):
        """
        Stop polling a wallet's balance.
        
        Args:
            task_id: Polling task ID from start_polling()
        """
        if task_id not in self._polling_tasks:
            logger.warning(f"No polling task with ID {task_id}")
            return
            
        # Cancel the task
        task = self._polling_tasks[task_id]
        task.cancel()
        
        try:
            await task
        except asyncio.CancelledError:
            pass
            
        # Clean up
        del self._polling_tasks[task_id]
        
        if task_id in self._last_balances:
            del self._last_balances[task_id]
            
        logger.info(f"Stopped balance polling for {task_id}")
    
    async def stop_all(self):
        """Stop all polling tasks."""
        task_ids = list(self._polling_tasks.keys())
        
        for task_id in task_ids:
            await self.stop_polling(task_id)
            
        logger.info(f"Stopped all {len(task_ids)} balance polling tasks")
    
    async def _poll_balance(
        self,
        wallet_address: str,
        token_address: str,
        target_balance: Optional[float],
        on_target_reached: Optional[Callable[[], Awaitable[None]]],
        interval: int
    ):
        """
        Poll a wallet's balance until cancelled.
        
        Args:
            wallet_address: Wallet address to poll
            token_address: Token contract address
            target_balance: Optional target balance to wait for
            on_target_reached: Callback to call when target reached
            interval: Polling interval in seconds
        """
        task_id = f"{wallet_address}_{token_address}"
        target_reached = False
        
        while True:
            try:
                # Get current balance
                balance_info = api_client.check_balance(wallet_address, token_address)
                
                # Extract current balance for the token
                current_balance = 0
                if isinstance(balance_info, dict) and 'balances' in balance_info:
                    for token_balance in balance_info['balances']:
                        # For SOL token specifically
                        if token_address is None or token_address == "So11111111111111111111111111111111111111112":
                            if token_balance.get('token') == "So11111111111111111111111111111111111111112" or token_balance.get('symbol') == "SOL":
                                current_balance = token_balance.get('amount', 0)
                                break
                        # For other specific tokens
                        elif token_balance.get('token') == token_address:
                            current_balance = token_balance.get('amount', 0)
                            break
                
                # Check if this is a change from last check
                last_balance = self._last_balances.get(task_id)
                
                if last_balance is not None and last_balance != current_balance:
                    # Balance changed, emit event
                    await event_system.publish(
                        BalanceChangeEvent(
                            wallet_address=wallet_address,
                            token_address=token_address,
                            previous_balance=last_balance,
                            new_balance=current_balance
                        )
                    )
                
                # Update last balance
                self._last_balances[task_id] = current_balance
                
                # Check if target reached
                if target_balance is not None and current_balance >= target_balance and not target_reached:
                    logger.info(
                        f"Target balance reached for {wallet_address}",
                        extra={
                            "wallet": wallet_address,
                            "token": token_address,
                            "current_balance": current_balance,
                            "target_balance": target_balance
                        }
                    )
                    
                    # Mark as reached so we don't call the callback again
                    target_reached = True
                    
                    if on_target_reached:
                        await on_target_reached()
                
                # Wait for next poll
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                logger.debug(f"Balance polling cancelled for {task_id}")
                raise
                
            except Exception as e:
                logger.error(
                    f"Error polling balance: {str(e)}",
                    extra={"wallet": wallet_address, "token": token_address}
                )
                
                # Wait a bit before retrying on error
                await asyncio.sleep(interval)


# Singleton instance
balance_poller = BalancePoller() 