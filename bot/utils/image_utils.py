"""
Telegram Image Processing Utility

Handles image uploads from Telegram users for token creation.
Provides download, storage, cleanup, and Pump.fun compatibility processing.
"""

import os
import time
from pathlib import Path
from typing import Optional, Tuple, Dict
from telegram import File
from loguru import logger

try:
    from PIL import Image, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL/Pillow not available - image processing will be limited")


class TelegramImageProcessor:
    """Handles Telegram image uploads and local storage with Pump.fun compatibility."""
    
    # Pump.fun compatible specifications
    PUMP_FUN_SIZE = (500, 500)  # Required dimensions for Pump.fun
    MAX_FILE_SIZE_MB = 20  # Telegram's limit
    SUPPORTED_FORMATS = {'JPEG', 'PNG', 'JPG'}
    QUALITY_SETTING = 85  # JPEG quality for size optimization
    
    def __init__(self, temp_dir: str = "temp/images"):
        """
        Initialize the image processor.
        
        Args:
            temp_dir: Directory for temporary image storage
        """
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        if not PIL_AVAILABLE:
            logger.warning("PIL not available - image processing will be limited to download only")
        
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
    
    def validate_image_file(self, file_path: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        Validate image file for processing compatibility.
        
        Args:
            file_path: Path to the image file
            
        Returns:
            Tuple of (is_valid, error_message, image_info)
        """
        try:
            path = Path(file_path)
            
            # Check file exists
            if not path.exists():
                return False, "Image file does not exist", None
            
            # Check file size
            file_size_mb = path.stat().st_size / (1024 * 1024)
            if file_size_mb > self.MAX_FILE_SIZE_MB:
                return False, f"Image too large: {file_size_mb:.1f}MB (max: {self.MAX_FILE_SIZE_MB}MB)", None
            
            if not PIL_AVAILABLE:
                # Basic validation without PIL
                return True, "", {"size_mb": file_size_mb, "processing_available": False}
            
            # Validate with PIL
            try:
                with Image.open(file_path) as img:
                    image_info = {
                        "format": img.format,
                        "size": img.size,
                        "mode": img.mode,
                        "size_mb": file_size_mb,
                        "processing_available": True
                    }
                    
                    # Check format support
                    if img.format not in self.SUPPORTED_FORMATS:
                        return False, f"Unsupported format: {img.format}. Supported: {', '.join(self.SUPPORTED_FORMATS)}", image_info
                    
                    return True, "", image_info
                    
            except Exception as e:
                return False, f"Invalid image file: {str(e)}", None
                
        except Exception as e:
            logger.error(f"Error validating image {file_path}: {e}")
            return False, f"Validation error: {str(e)}", None
    
    def process_for_pump_fun(self, input_path: str, user_id: int) -> Tuple[bool, str, Optional[str]]:
        """
        Process image to meet Pump.fun requirements (500x500, optimized).
        
        Args:
            input_path: Path to input image
            user_id: User ID for unique output filename
            
        Returns:
            Tuple of (success, message, output_path)
        """
        if not PIL_AVAILABLE:
            logger.warning("PIL not available - returning original image without processing")
            return True, "Image processing unavailable - using original", input_path
        
        try:
            # Validate input
            is_valid, error_msg, image_info = self.validate_image_file(input_path)
            if not is_valid:
                return False, error_msg, None
            
            # Generate output filename
            timestamp = int(time.time())
            output_filename = f"pump_ready_{user_id}_{timestamp}.jpg"
            output_path = self.temp_dir / output_filename
            
            # Process image
            with Image.open(input_path) as img:
                # Convert to RGB if necessary (for JPEG output)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Create white background for transparency
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Resize to 500x500 with proper aspect ratio handling
                img = ImageOps.fit(img, self.PUMP_FUN_SIZE, Image.Resampling.LANCZOS)
                
                # Save with optimization
                img.save(
                    output_path,
                    'JPEG',
                    quality=self.QUALITY_SETTING,
                    optimize=True
                )
            
            # Verify output
            if not output_path.exists():
                return False, "Failed to create processed image", None
            
            output_size_mb = output_path.stat().st_size / (1024 * 1024)
            
            logger.info(f"Processed image for user {user_id}: "
                       f"{image_info['size']} → {self.PUMP_FUN_SIZE}, "
                       f"{image_info['size_mb']:.1f}MB → {output_size_mb:.1f}MB")
            
            return True, f"Image processed successfully ({self.PUMP_FUN_SIZE[0]}x{self.PUMP_FUN_SIZE[1]}, {output_size_mb:.1f}MB)", str(output_path)
            
        except Exception as e:
            logger.error(f"Error processing image for user {user_id}: {e}")
            return False, f"Processing failed: {str(e)}", None
    
    async def download_and_process(self, file: File, user_id: int) -> Tuple[bool, str, Optional[str], Optional[Dict]]:
        """
        Complete workflow: download from Telegram and process for Pump.fun.
        
        Args:
            file: Telegram File object
            user_id: User ID for tracking
            
        Returns:
            Tuple of (success, message, final_path, processing_info)
        """
        processing_info = {
            "download_success": False,
            "validation_success": False,
            "processing_success": False,
            "original_path": None,
            "final_path": None,
            "processing_time": 0
        }
        
        start_time = time.time()
        
        try:
            # Step 1: Download from Telegram
            try:
                original_path = await self.download_telegram_photo(file, user_id)
                processing_info["download_success"] = True
                processing_info["original_path"] = original_path
                logger.info(f"Downloaded image for user {user_id}: {original_path}")
            except Exception as e:
                return False, f"Download failed: {str(e)}", None, processing_info
            
            # Step 2: Validate
            is_valid, error_msg, image_info = self.validate_image_file(original_path)
            if not is_valid:
                return False, f"Invalid image: {error_msg}", None, processing_info
            
            processing_info["validation_success"] = True
            processing_info["image_info"] = image_info
            
            # Step 3: Process for Pump.fun
            success, process_msg, final_path = self.process_for_pump_fun(original_path, user_id)
            if not success:
                return False, f"Processing failed: {process_msg}", None, processing_info
            
            processing_info["processing_success"] = True
            processing_info["final_path"] = final_path
            processing_info["processing_time"] = time.time() - start_time
            
            return True, f"Image ready for Pump.fun: {process_msg}", final_path, processing_info
            
        except Exception as e:
            processing_info["processing_time"] = time.time() - start_time
            logger.error(f"Complete processing failed for user {user_id}: {e}")
            return False, f"Processing pipeline failed: {str(e)}", None, processing_info
        
    def cleanup_temp_files(self, user_id: int, keep_latest: bool = False) -> int:
        """
        Clean up old temp files for a specific user.
        
        Args:
            user_id: User ID to clean files for
            keep_latest: Whether to keep the most recent file
            
        Returns:
            Number of files cleaned up
        """
        cleaned_count = 0
        patterns = [f"token_image_{user_id}_*.jpg", f"pump_ready_{user_id}_*.jpg"]
        
        try:
            all_files = []
            for pattern in patterns:
                all_files.extend(list(self.temp_dir.glob(pattern)))
            
            # Sort by modification time (newest first)
            all_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            # Keep latest if requested
            files_to_delete = all_files[1:] if keep_latest and all_files else all_files
            
            for file_path in files_to_delete:
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
        Get comprehensive information about a local image file.
        
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
            basic_info = {
                "filename": path.name,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "exists": True,
                "path": str(path),
                "modified_time": stat.st_mtime
            }
            
            if not PIL_AVAILABLE:
                basic_info["processing_available"] = False
                return basic_info
            
            # Add detailed image information
            try:
                with Image.open(file_path) as img:
                    basic_info.update({
                        "format": img.format,
                        "dimensions": img.size,
                        "width": img.size[0],
                        "height": img.size[1],
                        "mode": img.mode,
                        "is_square": img.size[0] == img.size[1],
                        "aspect_ratio": round(img.size[0] / img.size[1], 2) if img.size[1] > 0 else 0,
                        "processing_available": True,
                        "pump_fun_ready": img.size == self.PUMP_FUN_SIZE and img.format in self.SUPPORTED_FORMATS
                    })
            except Exception as e:
                logger.warning(f"Could not read image details for {file_path}: {e}")
                basic_info["processing_available"] = False
                
            return basic_info
            
        except Exception as e:
            logger.error(f"Error getting file info for {file_path}: {e}")
            return None 