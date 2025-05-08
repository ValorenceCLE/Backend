from celery import Celery
import redis
import logging
from celery.signals import worker_shutdown, worker_ready, task_failure, task_success
import os  # Import os to access CPU core count

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set to DEBUG for more verbose logging

# Set task-related loggers to INFO
logging.getLogger('app.core.tasks.rule_tasks').setLevel(logging.INFO)
logging.getLogger('app.core.tasks.sensor_tasks').setLevel(logging.INFO)

# Filter out noisy loggers
logging.getLogger('celery').setLevel(logging.WARNING)
logging.getLogger('celery.task').setLevel(logging.WARNING)
logging.getLogger('celery.worker').setLevel(logging.WARNING)

# Create Celery instance
app = Celery(
    'backend',
    broker='redis://redis:6379/0',
    backend='redis://redis:6379/0',
    include=[
        'app.core.tasks.sensor_tasks',
        'app.core.tasks.relay_tasks',
        'app.core.tasks.rule_tasks',
        'app.core.tasks.monitoring_tasks'
    ]
)

# Configure Celery
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=4,  # Prefetch up to 4 tasks to improve throughput under high load
    worker_max_tasks_per_child=100,  # Restart workers after 100 tasks to prevent memory leaks and ensure clean state
    worker_max_memory_per_child=150000,  # Restart worker if memory exceeds ~150MB to prevent memory bloat
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=300,  # Set a time limit on tasks to prevent hanging, adjusted for longer tasks
    worker_hijack_root_logger=False,
    worker_log_color=False,
    worker_redirect_stdouts=False,
    worker_redirect_stdouts_level='INFO',
    beat_schedule={
        'read-sensors-every-5-seconds': {
            'task': 'app.core.tasks.sensor_tasks.read_all_sensors',
            'schedule': 10.0,
        },
        'check-schedules-every-minute': {
            'task': 'app.core.tasks.relay_tasks.check_schedules',
            'schedule': 45.0,
        },
        'monitor-system-every-10-seconds': {
            'task': 'app.core.tasks.monitoring_tasks.monitor_system',
            'schedule': 16.0,
        },
        'check-network-every-minute': {
            'task': 'app.core.tasks.monitoring_tasks.check_network_connectivity',
            'schedule': 31.0,
        }
    }
)

@worker_ready.connect
def check_redis_connection(**kwargs):
    """Check Redis connection on worker startup"""
    try:
        redis_client = redis.Redis.from_url('redis://redis:6379/0')
        redis_client.ping()
        logger.info("Successfully connected to Redis")
        from app import worker
        worker.init_worker()
    except redis.ConnectionError:
        logger.error("Cannot connect to Redis! Celery worker will not function properly.")

@task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    """Log task failures with details"""
    logger.error(f"Task {sender.name}[{task_id}] failed: {exception}")

@task_success.connect
def handle_task_success(sender=None, result=None, **kwargs):
    """Log task successes (optional - can be commented out to reduce log volume)"""
    logger.debug(f"Task {sender.name} completed successfully")

@worker_shutdown.connect
def cleanup_resources(**kwargs):
    """Clean up resources when worker shuts down"""
    logger.info("Cleaning up resources during worker shutdown")