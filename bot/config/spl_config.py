"""
SPL Token Trading Configuration for Telegram Bot.
Integrates the existing buy_sell_config.py with Telegram session management.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Union
from enum import Enum
import json
import uuid
from pathlib import Path

from ..scripts.buy_sell_config import (
    SwapConfiguration, 
    TokenConfig, 
    AmountConfig, 
    ExecutionConfig,
    OperationType,
    AmountStrategy,
    ExecutionMode,
    ConfigurationManager
)
# Import ConversationState values directly to avoid circular import
class ConversationState:
    SPL_OPERATION_CHOICE = 20
    SPL_TOKEN_PAIR = 21
    SPL_AMOUNT_STRATEGY = 22
    SPL_EXECUTION_MODE = 23
    SPL_PREVIEW = 24
    SPL_EXECUTION = 25

# Re-export for convenience
__all__ = [
    'SwapConfiguration', 'TokenConfig', 'AmountConfig', 'ExecutionConfig',
    'OperationType', 'AmountStrategy', 'ExecutionMode',
    'TelegramSplConfig', 'TelegramSplConfigManager'
]


@dataclass
class TelegramSplConfig:
    """Extended SPL configuration for Telegram bot sessions."""
    
    # Core swap configuration
    swap_config: Optional[SwapConfiguration] = None
    
    # Telegram session specific
    user_id: int = 0
    chat_id: int = 0
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conversation_state: int = ConversationState.SPL_OPERATION_CHOICE
    
    # Progress tracking
    step_completed: Dict[str, bool] = field(default_factory=dict)
    temp_data: Dict[str, Any] = field(default_factory=dict)
    
    # Wallet context
    mother_wallet_address: Optional[str] = None
    child_wallets: List[str] = field(default_factory=list)
    child_private_keys: List[str] = field(default_factory=list)
    
    # Execution tracking
    execution_id: Optional[str] = None
    execution_progress: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize default step completion tracking."""
        if not self.step_completed:
            self.step_completed = {
                'operation_selected': False,
                'token_pair_configured': False,
                'amount_strategy_set': False,
                'execution_mode_set': False,
                'preview_confirmed': False
            }
    
    def is_ready_for_execution(self) -> bool:
        """Check if configuration is complete and ready for execution."""
        return (
            self.swap_config is not None and
            all(self.step_completed.values()) and
            self.mother_wallet_address is not None and
            len(self.child_wallets) > 0
        )
    
    def get_progress_percentage(self) -> int:
        """Get configuration progress as percentage."""
        completed_steps = sum(1 for completed in self.step_completed.values() if completed)
        total_steps = len(self.step_completed)
        return int((completed_steps / total_steps) * 100) if total_steps > 0 else 0


class TelegramSplConfigManager:
    """Manages SPL configurations for Telegram bot sessions."""
    
    def __init__(self, config_dir: str = "data/spl_sessions"):
        """Initialize the Telegram SPL configuration manager."""
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.core_manager = ConfigurationManager("data/spl_configs")
        
        # Active sessions cache
        self._sessions: Dict[int, TelegramSplConfig] = {}
    
    def get_session(self, user_id: int, chat_id: int = None) -> TelegramSplConfig:
        """Get or create a session for the user."""
        if user_id not in self._sessions:
            self._sessions[user_id] = TelegramSplConfig(
                user_id=user_id,
                chat_id=chat_id or user_id
            )
        return self._sessions[user_id]
    
    def update_session(self, user_id: int, **updates) -> TelegramSplConfig:
        """Update session with new data."""
        session = self.get_session(user_id)
        
        for key, value in updates.items():
            if hasattr(session, key):
                setattr(session, key, value)
            else:
                session.temp_data[key] = value
        
        return session
    
    def create_swap_config(self, user_id: int, operation: OperationType) -> SwapConfiguration:
        """Create a new swap configuration for the session."""
        session = self.get_session(user_id)
        
        # Create basic configuration
        token_config = TokenConfig(input_token="", output_token="")
        amount_config = AmountConfig(strategy=AmountStrategy.FIXED, base_amount=0.1)
        execution_config = ExecutionConfig()
        
        swap_config = SwapConfiguration(
            operation=operation,
            token_config=token_config,
            amount_config=amount_config,
            execution_config=execution_config,
            dry_run=True,  # Start with dry run by default
            generate_report=True
        )
        
        session.swap_config = swap_config
        session.step_completed['operation_selected'] = True
        return swap_config
    
    def update_token_config(self, user_id: int, input_token: str, output_token: str) -> TokenConfig:
        """Update token configuration for the session."""
        session = self.get_session(user_id)
        if not session.swap_config:
            raise ValueError("No swap configuration found. Please start over.")
        
        session.swap_config.token_config.input_token = input_token
        session.swap_config.token_config.output_token = output_token
        session.step_completed['token_pair_configured'] = True
        
        return session.swap_config.token_config
    
    def update_amount_config(self, user_id: int, strategy: AmountStrategy, **kwargs) -> AmountConfig:
        """Update amount configuration for the session."""
        session = self.get_session(user_id)
        if not session.swap_config:
            raise ValueError("No swap configuration found. Please start over.")
        
        # Update strategy
        session.swap_config.amount_config.strategy = strategy
        
        # Update strategy-specific parameters
        if strategy == AmountStrategy.FIXED:
            session.swap_config.amount_config.base_amount = kwargs.get('base_amount', 0.1)
        elif strategy == AmountStrategy.PERCENTAGE:
            session.swap_config.amount_config.percentage = kwargs.get('percentage', 0.5)
        elif strategy == AmountStrategy.RANDOM:
            session.swap_config.amount_config.min_amount = kwargs.get('min_amount', 0.05)
            session.swap_config.amount_config.max_amount = kwargs.get('max_amount', 0.25)
        elif strategy == AmountStrategy.CUSTOM:
            session.swap_config.amount_config.custom_amounts = kwargs.get('custom_amounts', [])
        
        session.step_completed['amount_strategy_set'] = True
        return session.swap_config.amount_config
    
    def update_execution_config(self, user_id: int, mode: ExecutionMode, **kwargs) -> ExecutionConfig:
        """Update execution configuration for the session."""
        session = self.get_session(user_id)
        if not session.swap_config:
            raise ValueError("No swap configuration found. Please start over.")
        
        # Update execution mode
        session.swap_config.execution_config.mode = mode
        
        # Update mode-specific parameters
        if mode == ExecutionMode.PARALLEL:
            session.swap_config.execution_config.max_concurrent = kwargs.get('max_concurrent', 5)
        elif mode == ExecutionMode.BATCH:
            session.swap_config.execution_config.batch_size = kwargs.get('batch_size', 10)
            session.swap_config.execution_config.delay_between_batches = kwargs.get('delay_between_batches', 2.0)
        
        # Update common parameters
        if 'slippage_bps' in kwargs:
            session.swap_config.execution_config.slippage_bps = kwargs['slippage_bps']
        
        session.step_completed['execution_mode_set'] = True
        return session.swap_config.execution_config
    
    def set_wallet_context(self, user_id: int, mother_wallet: str, child_wallets: List[str], 
                          child_private_keys: List[str] = None) -> None:
        """Set wallet context for the session."""
        session = self.get_session(user_id)
        session.mother_wallet_address = mother_wallet
        session.child_wallets = child_wallets
        if child_private_keys:
            session.child_private_keys = child_private_keys
        
        # Update swap config if exists
        if session.swap_config:
            session.swap_config.mother_wallet_address = mother_wallet
    
    def confirm_preview(self, user_id: int) -> bool:
        """Confirm the preview and mark ready for execution."""
        session = self.get_session(user_id)
        if not session.swap_config:
            return False
        
        session.step_completed['preview_confirmed'] = True
        return session.is_ready_for_execution()
    
    def save_session(self, user_id: int) -> bool:
        """Save session to file."""
        if user_id not in self._sessions:
            return False
        
        session = self._sessions[user_id]
        session_file = self.config_dir / f"session_{user_id}_{session.session_id}.json"
        
        try:
            # Convert session to dict for JSON serialization
            session_data = {
                'user_id': session.user_id,
                'chat_id': session.chat_id,
                'session_id': session.session_id,
                'conversation_state': session.conversation_state,
                'step_completed': session.step_completed,
                'temp_data': session.temp_data,
                'mother_wallet_address': session.mother_wallet_address,
                'child_wallets': session.child_wallets,
                'execution_id': session.execution_id,
                'execution_progress': session.execution_progress
            }
            
            # Save swap config separately if exists
            if session.swap_config:
                config_file = self.config_dir / f"config_{user_id}_{session.session_id}.json"
                self.core_manager.save_config(session.swap_config, str(config_file))
                session_data['swap_config_file'] = str(config_file)
            
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"Error saving session: {e}")
            return False
    
    def load_session(self, user_id: int, session_id: str) -> Optional[TelegramSplConfig]:
        """Load session from file."""
        session_file = self.config_dir / f"session_{user_id}_{session_id}.json"
        
        if not session_file.exists():
            return None
        
        try:
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            # Create session object
            session = TelegramSplConfig(
                user_id=session_data['user_id'],
                chat_id=session_data['chat_id'],
                session_id=session_data['session_id'],
                conversation_state=session_data.get('conversation_state', ConversationState.SPL_OPERATION_CHOICE),
                step_completed=session_data.get('step_completed', {}),
                temp_data=session_data.get('temp_data', {}),
                mother_wallet_address=session_data.get('mother_wallet_address'),
                child_wallets=session_data.get('child_wallets', []),
                execution_id=session_data.get('execution_id'),
                execution_progress=session_data.get('execution_progress', {})
            )
            
            # Load swap config if exists
            if 'swap_config_file' in session_data:
                config_file = Path(session_data['swap_config_file'])
                if config_file.exists():
                    session.swap_config = self.core_manager.load_config(str(config_file))
            
            self._sessions[user_id] = session
            return session
            
        except Exception as e:
            print(f"Error loading session: {e}")
            return None
    
    def clear_session(self, user_id: int) -> None:
        """Clear session data."""
        if user_id in self._sessions:
            del self._sessions[user_id]
    
    def list_user_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """List all sessions for a user."""
        sessions = []
        
        for session_file in self.config_dir.glob(f"session_{user_id}_*.json"):
            try:
                with open(session_file, 'r') as f:
                    session_data = json.load(f)
                
                sessions.append({
                    'session_id': session_data['session_id'],
                    'created_at': session_file.stat().st_ctime,
                    'conversation_state': session_data.get('conversation_state'),
                    'progress': len([v for v in session_data.get('step_completed', {}).values() if v])
                })
                
            except Exception:
                continue  # Skip corrupted files
        
        return sorted(sessions, key=lambda x: x['created_at'], reverse=True)


# Global instance for the bot
telegram_spl_manager = TelegramSplConfigManager() 