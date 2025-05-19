"""
Common utilities for Celery tasks.

This module provides shared functions, decorators, and patterns
for standardizing task behavior across the application.
"""
import asyncio
import functools
import logging
import time
from typing import Callable, Any

logger = logging.getLogger(__name__)

def run_task_with_new_loop(func):
    """
    Decorator for Celery tasks that use asyncio.
    Creates a new event loop for each task invocation.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Create a new event loop for this task
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Important: Set the loop's debug to False to avoid logging issues
        loop.set_debug(False)
        
        try:
            # Run the async function to completion
            return loop.run_until_complete(func(*args, **kwargs))
        finally:
            # Clean up pending tasks
            try:
                pending = asyncio.all_tasks(loop)
                if pending:
                    for task in pending:
                        if not task.done():
                            task.cancel()
                    
                    # Use a timeout to avoid hanging indefinitely
                    loop.run_until_complete(
                        asyncio.wait_for(
                            asyncio.gather(*pending, return_exceptions=True),
                            timeout=5.0
                        )
                    )
            except Exception as e:
                logger.warning(f"Error cleaning up tasks: {e}")
                # Continue with loop closure even if cleanup fails
                
            # Close the loop
            loop.close()
            
    return wrapper

class TaskMetrics:
    """
    Utility for tracking and logging task execution metrics.
    
    Usage:
        with TaskMetrics("task_name") as metrics:
            # Do work
            metrics.increment("processed", 5)
            # More work
            metrics.increment("errors", 1)
    """
    
    def __init__(self, task_name: str):
        self.task_name = task_name
        self.start_time = None
        self.metrics = {
            "processed": 0,
            "errors": 0,
            "warnings": 0,
        }
        
    def __enter__(self):
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.metrics["duration"] = round(duration, 3)
        
        # Log task completion with metrics
        metric_strs = [f"{k}={v}" for k, v in self.metrics.items()]
        if exc_type:
            logger.error(f"Task {self.task_name} failed after {duration:.3f}s: {exc_val} | {', '.join(metric_strs)}")
        else:
            logger.debug(f"Task {self.task_name} completed in {duration:.3f}s | {', '.join(metric_strs)}")
        
        return False  # Don't suppress exceptions
    
    def increment(self, metric: str, value: int = 1):
        """Increment a metric value."""
        if metric in self.metrics:
            self.metrics[metric] += value
        else:
            self.metrics[metric] = value
            
    def set(self, metric: str, value: Any):
        """Set a metric value."""
        self.metrics[metric] = value

def retry_with_backoff(retries: int = 3, initial_delay: float = 0.1, 
                      backoff_factor: float = 2.0, exceptions: tuple = (Exception,)) -> Callable:
    """
    Decorator for retrying a function with exponential backoff.
    
    Args:
        retries: Maximum number of retries
        initial_delay: Initial backoff delay (seconds)
        backoff_factor: Backoff multiplication factor
        exceptions: Tuple of exceptions to catch for retry
        
    Usage:
        @retry_with_backoff(retries=3, initial_delay=0.5)
        def function_that_might_fail():
            # implementation
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < retries:
                        sleep_time = delay * (backoff_factor ** attempt)
                        logger.warning(f"Retry {attempt+1}/{retries} for {func.__name__} after {sleep_time:.3f}s: {e}")
                        time.sleep(sleep_time)
            
            # If we get here, all retries failed
            logger.error(f"All {retries} retries failed for {func.__name__}: {last_exception}")
            raise last_exception
        
        return wrapper
    return decorator