from celery import Celery
import redis
import logging
from celery.signals import worker_shutdown, worker_ready, task_failure, task_success

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
    worker_concurrency=4,  # Increase to handle multiple tasks
    worker_prefetch_multiplier=1,  # Only prefetch one task at a time
    worker_max_tasks_per_child=50,  # Restart workers occasionally to prevent memory leaks
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=30,  # Set a time limit on tasks to prevent hanging
    worker_hijack_root_logger=False,
    worker_log_color=False,
    worker_redirect_stdouts=False,
    worker_redirect_stdouts_level='ERROR',
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