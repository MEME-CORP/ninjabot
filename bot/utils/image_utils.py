"""
Telegram Image Processing Utility

Handles image uploads from Telegram users for token creation.
Provides download, storage, and cleanup functionality.
"""

import os
import time
from pathlib import Path
from typing import Optional
from telegram import File
from loguru import logger


class TelegramImageProcessor:
    """Handles Telegram image uploads and local storage."""
    
    def __init__(self, temp_dir: str = "temp/images"):
        """
        Initialize the image processor.
        
        Args:
            temp_dir: Directory for temporary image storage
        """
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
    async def download_telegram_photo(self, file: File, user_id: int) -> str:
        """
        Download photo from Telegram and return local path.
        
        Args:
            file: Telegram File object
            user_id: User ID for unique filename
            
        Returns:
            Local file path as string
            
        Raises:
            Exception: If download fails
        """
        try:
            # Generate unique filename with timestamp
            timestamp = int(time.time())
            filename = f"token_image_{user_id}_{timestamp}.jpg"
            local_path = self.temp_dir / filename
            
            # Download from Telegram to local storage
            await file.download_to_drive(local_path)
            
            # Verify file was created and has content
            if not local_path.exists() or local_path.stat().st_size == 0:
                raise Exception(f"Downloaded file is empty or doesn't exist: {local_path}")
            
            logger.info(f"Downloaded Telegram image to {local_path} ({local_path.stat().st_size} bytes)")
            
            return str(local_path)
            
        except Exception as e:
            logger.error(f"Failed to download Telegram image: {e}")
            raise Exception(f"Image download failed: {str(e)}")
        
    def cleanup_temp_files(self, user_id: int) -> int:
        """
        Clean up old temp files for a specific user.
        
        Args:
            user_id: User ID to clean files for
            
        Returns:
            Number of files cleaned up
        """
        cleaned_count = 0
        pattern = f"token_image_{user_id}_*.jpg"
        
        try:
            for file_path in self.temp_dir.glob(pattern):
                try:
                    file_path.unlink()
                    logger.info(f"Cleaned up temp file: {file_path}")
                    cleaned_count += 1
                except Exception as e:
                    logger.warning(f"Failed to cleanup {file_path}: {e}")
                    
        except Exception as e:
            logger.error(f"Error during cleanup for user {user_id}: {e}")
            
        return cleaned_count
        
    def get_file_info(self, file_path: str) -> Optional[dict]:
        """
        Get information about a local image file.
        
        Args:
            file_path: Path to the image file
            
        Returns:
            Dictionary with file info or None if file doesn't exist
        """
        try:
            path = Path(file_path)
            if not path.exists():
                return None
                
            stat = path.stat()
            return {
                "filename": path.name,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "exists": True,
                "path": str(path)
            }
            
        except Exception as e:
            logger.error(f"Error getting file info for {file_path}: {e}")
            return None 