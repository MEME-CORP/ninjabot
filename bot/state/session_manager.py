from typing import Dict, Any, Optional
import time
from loguru import logger
from bot.config import CONVERSATION_TIMEOUT

class SessionManager:
    """
    Manages user session data for conversations.
    
    This class provides methods to store, retrieve, and manage user session data
    with timeouts to prevent stale sessions.
    """
    
    def __init__(self):
        """Initialize the session manager with an empty sessions dictionary."""
        # Structure: {user_id: {'last_updated': timestamp, 'data': {...}}}
        self._sessions: Dict[int, Dict[str, Any]] = {}
    
    def get_session_data(self, user_id: int) -> Dict[str, Any]:
        """
        Get the session data for a user.
        
        Args:
            user_id: The Telegram user ID
            
        Returns:
            The session data dictionary, or an empty dict if no session exists
        """
        session = self._sessions.get(user_id)
        
        if not session:
            # No session exists
            return {}
            
        if self._is_session_expired(session):
            # Session expired, clean it up
            logger.info(f"Session expired for user {user_id}. Cleaning up.")
            self.clear_session(user_id)
            return {}
            
        # Update last accessed time
        session['last_updated'] = time.time()
        return session.get('data', {})
    
    def set_session_data(self, user_id: int, data: Dict[str, Any]):
        """
        Set or update the session data for a user.
        
        Args:
            user_id: The Telegram user ID
            data: The session data to store
        """
        current_time = time.time()
        
        if user_id in self._sessions:
            # Update existing session
            self._sessions[user_id]['last_updated'] = current_time
            self._sessions[user_id]['data'] = data
        else:
            # Create new session
            self._sessions[user_id] = {
                'last_updated': current_time,
                'data': data
            }
            
        logger.debug(
            f"Session data updated for user {user_id}",
            extra={"user_id": user_id, "session_keys": list(data.keys())}
        )
    
    def update_session_value(self, user_id: int, key: str, value: Any):
        """
        Update a single value in the session data.
        
        Args:
            user_id: The Telegram user ID
            key: The key to update
            value: The new value
        """
        session_data = self.get_session_data(user_id)
        session_data[key] = value
        self.set_session_data(user_id, session_data)
    
    def get_session_value(self, user_id: int, key: str, default: Any = None) -> Any:
        """
        Get a single value from the session data.
        
        Args:
            user_id: The Telegram user ID
            key: The key to retrieve
            default: Default value if key doesn't exist
            
        Returns:
            The value for the key, or the default if not found
        """
        session_data = self.get_session_data(user_id)
        return session_data.get(key, default)
    
    def clear_session(self, user_id: int):
        """
        Clear the session for a user.
        
        Args:
            user_id: The Telegram user ID
        """
        if user_id in self._sessions:
            del self._sessions[user_id]
            logger.debug(f"Session cleared for user {user_id}")
    
    def refresh_session(self, user_id: int):
        """
        Refresh the session timestamp to prevent timeout during long operations.
        
        Args:
            user_id: The Telegram user ID
        """
        if user_id in self._sessions:
            self._sessions[user_id]['last_updated'] = time.time()
            logger.debug(f"Session refreshed for user {user_id}")
    
    def _is_session_expired(self, session: Dict[str, Any]) -> bool:
        """
        Check if a session has expired.
        
        Args:
            session: The session dictionary
            
        Returns:
            True if the session has expired, False otherwise
        """
        last_updated = session.get('last_updated', 0)
        current_time = time.time()
        return (current_time - last_updated) > CONVERSATION_TIMEOUT
        
    def cleanup_expired_sessions(self):
        """
        Remove all expired sessions.
        
        This method should be called periodically to clean up stale sessions.
        """
        expired_users = []
        
        for user_id, session in self._sessions.items():
            if self._is_session_expired(session):
                expired_users.append(user_id)
                
        for user_id in expired_users:
            self.clear_session(user_id)
            
        if expired_users:
            logger.info(f"Cleaned up {len(expired_users)} expired sessions")

# Singleton instance for global access
session_manager = SessionManager() 