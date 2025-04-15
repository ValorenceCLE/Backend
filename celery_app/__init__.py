from celery import Celery
import redis
import logging
from celery.signals import worker_shutdown, worker_ready
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)
logging.getLogger('celery').setLevel(logging.ERROR)  # Only show errors
logging.getLogger('celery.task').setLevel(logging.ERROR)
logging.getLogger('celery.worker').setLevel(logging.ERROR)
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
    worker_concurrency=1,
    worker_pool='prefork',
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    worker_hijack_root_logger=False,  # Don't hijack the root logger
    worker_log_color=False,           # Disable colors in logs
    worker_log_format='',             # Empty format to disable logging
    worker_task_log_format='',        # Empty format to disable task logging
    worker_redirect_stdouts = False,
    worker_redirect_stdouts_level = 'ERROR',
    beat_schedule={
        'read-sensors-every-5-seconds': {
            'task': 'app.core.tasks.sensor_tasks.read_all_sensors',
            'schedule': 5.0,
        },
        'check-schedules-every-minute': {
            'task': 'app.core.tasks.relay_tasks.check_schedules',
            'schedule': 60.0,
        },
        'monitor-system-every-10-seconds': {
            'task': 'app.core.tasks.monitoring_tasks.monitor_system',
            'schedule': 10.0,
        },
        'check-network-every-minute': {
            'task': 'app.core.tasks.monitoring_tasks.check_network_connectivity',
            'schedule': 60.0,
        }
    }
)


@worker_ready.connect
def check_redis_connection(**kwargs):
    """Check Redis connection on worker startup"""
    try:
        redis_client = redis.Redis.from_url('redis://redis:6379/0')
        redis_client.ping()
        logger.debug("Successfully connected to Redis")
    except redis.ConnectionError:
        logger.error("Cannot connect to Redis! Celery worker will not function properly.")

@worker_shutdown.connect
def cleanup_resources(**kwargs):
    """Clean up GPIO resources when worker shuts down"""
    from app.services.controller import RelayControl
    logger.info("Cleaning up GPIO resources")
    RelayControl.cleanup()