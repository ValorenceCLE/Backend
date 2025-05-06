# app/worker.py
import asyncio
import logging
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set to DEBUG for more verbose logging

def init_worker():
    """Initialize services when the celery worker starts."""
    logger.info("Initializing worker services...")
    
    # Only attempt initialization if we're in a worker process
    if os.environ.get('ROLE') == 'worker':
        try:
            # Use a new event loop explicitly
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Import config manager inside function to avoid circular imports
            from app.core.services.config_manager import config_manager
            
            # Run initialization in the loop
            logger.info("Initializing configuration manager in worker process")
            success = loop.run_until_complete(config_manager.initialize())
            
            if success:
                logger.info("Configuration manager initialized successfully in worker process")
            else:
                logger.error("Failed to initialize configuration manager in worker process")
            
            loop.close()
        except Exception as e:
            logger.error(f"Error initializing configuration manager in worker: {e}")
    
    logger.info("Worker initialization complete")

# Don't automatically run initialization when the module is imported
# Let Celery's import mechanism handle this instead