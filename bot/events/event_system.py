import asyncio
import time
import random
from typing import Dict, List, Any, Optional, Callable, Awaitable
from loguru import logger

class Event:
    """Base event class for the event system."""
    
    def __init__(self, event_type: str, data: Dict[str, Any]):
        """
        Initialize a new event.
        
        Args:
            event_type: Type of event
            data: Event data
        """
        self.event_type = event_type
        self.data = data
        self.timestamp = time.time()
    
    def __str__(self) -> str:
        """String representation of the event."""
        return f"Event(type={self.event_type}, data={self.data})"


class TransactionSentEvent(Event):
    """Event emitted when a transaction is sent."""
    
    def __init__(self, tx_hash: str, from_address: str, to_address: str, amount: float, token_symbol: str = "tokens"):
        """
        Initialize a transaction sent event.
        
        Args:
            tx_hash: Transaction hash
            from_address: Sender address
            to_address: Recipient address
            amount: Transaction amount
            token_symbol: Token symbol or name
        """
        super().__init__("transaction_sent", {
            "tx_hash": tx_hash,
            "from": from_address,
            "to": to_address,
            "amount": amount,
            "token_symbol": token_symbol,
            "status": "sent"
        })


class TransactionConfirmedEvent(Event):
    """Event emitted when a transaction is confirmed."""
    
    def __init__(self, tx_hash: str, from_address: str, to_address: str, amount: float, token_symbol: str = "tokens"):
        """
        Initialize a transaction confirmed event.
        
        Args:
            tx_hash: Transaction hash
            from_address: Sender address
            to_address: Recipient address
            amount: Transaction amount
            token_symbol: Token symbol or name
        """
        super().__init__("transaction_confirmed", {
            "tx_hash": tx_hash,
            "from": from_address,
            "to": to_address,
            "amount": amount,
            "token_symbol": token_symbol,
            "status": "confirmed"
        })


class TransactionFailedEvent(Event):
    """Event emitted when a transaction fails."""
    
    def __init__(
        self, 
        tx_hash: str, 
        from_address: str, 
        to_address: str, 
        amount: float, 
        error: str,
        token_symbol: str = "tokens"
    ):
        """
        Initialize a transaction failed event.
        
        Args:
            tx_hash: Transaction hash
            from_address: Sender address
            to_address: Recipient address
            amount: Transaction amount
            error: Error message
            token_symbol: Token symbol or name
        """
        super().__init__("transaction_failed", {
            "tx_hash": tx_hash,
            "from": from_address,
            "to": to_address,
            "amount": amount,
            "token_symbol": token_symbol,
            "error": error,
            "status": "failed"
        })


class TransactionRetryEvent(Event):
    """Event emitted when a transaction is retried."""
    
    def __init__(
        self, 
        tx_hash: str, 
        from_address: str, 
        to_address: str, 
        amount: float, 
        retry_count: int,
        token_symbol: str = "tokens"
    ):
        """
        Initialize a transaction retry event.
        
        Args:
            tx_hash: Transaction hash
            from_address: Sender address
            to_address: Recipient address
            amount: Transaction amount
            retry_count: Retry attempt number
            token_symbol: Token symbol or name
        """
        super().__init__("transaction_retry", {
            "tx_hash": tx_hash,
            "from": from_address,
            "to": to_address,
            "amount": amount,
            "token_symbol": token_symbol,
            "retry_count": retry_count,
            "status": "retrying"
        })


class BalanceChangeEvent(Event):
    """Event emitted when a wallet balance changes."""
    
    def __init__(
        self, 
        wallet_address: str, 
        token_address: str, 
        previous_balance: float, 
        new_balance: float,
        token_symbol: str = "tokens"
    ):
        """
        Initialize a balance change event.
        
        Args:
            wallet_address: Wallet address
            token_address: Token contract address
            previous_balance: Previous balance
            new_balance: New balance
            token_symbol: Token symbol or name
        """
        super().__init__("balance_change", {
            "wallet": wallet_address,
            "token": token_address,
            "previous_balance": previous_balance,
            "new_balance": new_balance,
            "token_symbol": token_symbol
        })


class EventSystem:
    """
    System for subscribing to and publishing events.
    
    This class provides methods to subscribe to events and publish events
    to subscribers asynchronously.
    """
    
    def __init__(self):
        """Initialize the event system."""
        self._subscribers: Dict[str, List[Callable[[Event], Awaitable[None]]]] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._background_task = None
    
    async def subscribe(self, event_type: str, callback: Callable[[Event], Awaitable[None]]):
        """
        Subscribe to an event type.
        
        Args:
            event_type: Type of event to subscribe to
            callback: Async callback function to call when event occurs
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
            
        self._subscribers[event_type].append(callback)
        logger.debug(f"Subscribed to {event_type} events")
    
    async def publish(self, event: Event):
        """
        Publish an event to subscribers.
        
        Args:
            event: Event to publish
        """
        await self._queue.put(event)
        logger.debug(f"Published {event.event_type} event")
    
    async def _process_events(self):
        """Process events from the queue and dispatch to subscribers."""
        while self._running:
            try:
                event = await self._queue.get()
                logger.debug(f"Processing {event.event_type} event")
                
                subscribers = self._subscribers.get(event.event_type, [])
                if subscribers:
                    await asyncio.gather(*(sub(event) for sub in subscribers))
                
                self._queue.task_done()
                
            except asyncio.CancelledError:
                logger.debug("Event processing task cancelled")
                break
                
            except Exception as e:
                logger.error(f"Error processing event: {str(e)}")
    
    async def start(self):
        """Start the event processing task."""
        if self._running:
            return
            
        self._running = True
        self._background_task = asyncio.create_task(self._process_events())
        logger.info("Event system started")
    
    async def stop(self):
        """Stop the event processing task."""
        if not self._running:
            return
            
        self._running = False
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
                
        logger.info("Event system stopped")
    
    
    # For testing purposes, simulate events for a run
    async def simulate_events_for_run(self, run_id: str, schedule: Dict[str, Any]):
        """
        Simulate events for a schedule run.
        
        Args:
            run_id: Schedule run ID
            schedule: Schedule information
        """
        transfers = schedule.get("transfers", [])
        
        for transfer in transfers:
            # Simulate transaction sent
            tx_hash = f"TXHash{random.randint(1000, 9999)}"
            
            await self.publish(TransactionSentEvent(
                tx_hash=tx_hash,
                from_address=transfer["from"],
                to_address=transfer["to"],
                amount=transfer["amount"]
            ))
            
            # Wait a bit
            await asyncio.sleep(1)
            
            # 80% chance of success, 20% chance of failure/retry
            if random.random() < 0.8:
                # Simulate confirmation
                await self.publish(TransactionConfirmedEvent(
                    tx_hash=tx_hash,
                    from_address=transfer["from"],
                    to_address=transfer["to"],
                    amount=transfer["amount"]
                ))
            else:
                # Simulate failure and retry
                await self.publish(TransactionFailedEvent(
                    tx_hash=tx_hash,
                    from_address=transfer["from"],
                    to_address=transfer["to"],
                    amount=transfer["amount"],
                    error="Transaction timed out"
                ))
                
                # Retry
                await self.publish(TransactionRetryEvent(
                    tx_hash=tx_hash,
                    from_address=transfer["from"],
                    to_address=transfer["to"],
                    amount=transfer["amount"],
                    retry_count=1
                ))
                
                # Simulate success on retry
                await asyncio.sleep(1)
                
                new_tx_hash = f"TXHashRetry{random.randint(1000, 9999)}"
                
                await self.publish(TransactionSentEvent(
                    tx_hash=new_tx_hash,
                    from_address=transfer["from"],
                    to_address=transfer["to"],
                    amount=transfer["amount"]
                ))
                
                await asyncio.sleep(1)
                
                await self.publish(TransactionConfirmedEvent(
                    tx_hash=new_tx_hash,
                    from_address=transfer["from"],
                    to_address=transfer["to"],
                    amount=transfer["amount"]
                ))
            
            # Wait a bit before next transfer
            await asyncio.sleep(2)


# Singleton instance
event_system = EventSystem() 