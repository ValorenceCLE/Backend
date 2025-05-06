# app/core/services/config_io.py
import json
import aiofiles
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set to DEBUG for more verbose logging

class ConfigIO:
    """
    Asynchronous configuration file I/O operations service.
    """
    @staticmethod
    async def read_json_file(file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Reads a JSON file asynchronously and returns its content as a dictionary.
        """
        try:
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return None
            
            async with aiofiles.open(file_path, "r") as file:
                content = await file.read()
                return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in file {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return None
        
    @staticmethod
    async def write_json_file(file_path: Path, data: Dict[str, Any]) -> bool:
        """
        Writes a dictionary to a JSON file asynchronously.
        """
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(file_path, "w") as file:
                await file.write(json.dumps(data, indent=4))
            logger.info(f"Successfully wrote to file: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error writing to file {file_path}: {e}")
            return False
    
    @staticmethod
    async def delete_file(file_path: Path) -> bool:
        """Delete a configuration file."""
        try:
            if file_path.exists():
                os.remove(file_path)
                logger.info(f"Configuration file deleted: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting configuration file {file_path}: {e}")
            return False