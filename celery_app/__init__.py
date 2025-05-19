"""
Celery application configuration.

This module configures the Celery application with optimized settings
for working with asyncio and hardware control.
"""
from celery import Celery
import redis
import logging
import time
from celery.signals import worker_shutdown, worker_ready, task_failure, task_success, task_retry

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Filter out noisy loggers
logging.getLogger('celery').setLevel(logging.WARNING)
logging.getLogger('celery.task').setLevel(logging.WARNING)
logging.getLogger('celery.worker').setLevel(logging.WARNING)

# Create Celery instance with better defaults
app = Celery(
    'backend',
    broker='redis://redis:6379/0',
    backend='redis://redis:6379/0',
    include=[
        'app.core.tasks.sensor_tasks',
        'app.core.tasks.relay_tasks',
        'app.core.tasks.rule_tasks',
    ]
)

# Performance-optimized configuration with better async handling
app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Disable prefork which causes problems with asyncio
    worker_pool='solo',  # Use solo pool for better asyncio compatibility
    
    # Worker settings
    worker_concurrency=1,  # Single process in solo mode
    worker_max_tasks_per_child=100,  # Restart workers frequently
    
    # Task execution
    task_time_limit=60,  # Kill tasks running longer than 60 seconds
    task_soft_time_limit=30,  # Warning at 30 seconds
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Timezone 
    timezone='UTC',
    enable_utc=True,
    
    # Logging
    worker_redirect_stdouts=False,
    worker_redirect_stdouts_level='ERROR',
    worker_log_format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    worker_task_log_format='%(asctime)s - %(name)s - %(levelname)s - %(task_name)s[%(task_id)s] - %(message)s',
    worker_hijack_root_logger=False,
    
    # Prevent overlapping tasks
    beat_max_loop_interval=5,  # Max seconds between checking schedule
    
    # Beat schedule with safer timing
    beat_schedule={
        'read-sensors-every-5-seconds': {
            'task': 'app.core.tasks.sensor_tasks.read_all_sensors',
            'schedule': 5.0,
            'options': {'expires': 4}  # Expire before next run to prevent overlap
        },
        'check-schedules-every-minute': {
            'task': 'app.core.tasks.relay_tasks.check_schedules',
            'schedule': 60.0,
            'options': {'expires': 55}  # Expire before next run to prevent overlap
        }
    }
)

@worker_ready.connect
def on_worker_ready(**kwargs):
    """Validate service connections on worker startup."""
    logger.info("Worker started - validating service connections")
    
    # Check Redis
    try:
        redis_client = redis.Redis.from_url('redis://redis:6379/0', socket_timeout=2.0)
        redis_client.ping()
        logger.info("✅ Redis connection verified")
    except Exception as e:
        logger.error(f"❌ Redis connection error: {e}")

@task_failure.connect
def log_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, **_):
    """Log detailed task failure information."""
    logger.error(
        f"❌ Task {sender.name}[{task_id}] failed: {exception}\n"
        f"  Args: {args}\n"
        f"  Kwargs: {kwargs}"
    )

@task_retry.connect
def log_task_retry(sender=None, request=None, reason=None, einfo=None, **_):
    """Log task retry information."""
    logger.warning(
        f"⚠️ Task {sender.name} retrying: {reason}\n"
        f"  Args: {request.args}\n"
        f"  Kwargs: {request.kwargs}"
    )

@worker_shutdown.connect
def cleanup_resources(**_):
    """Clean up resources during worker shutdown."""
    logger.info("🛑 Worker shutting down - cleaning up resources")
    
    # Sleep briefly to allow in-progress tasks to complete
    time.sleep(0.5)