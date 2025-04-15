from celery import Celery
import redis
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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
    worker_concurrency=2,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
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

# Add Redis connection error handling
from celery.signals import worker_ready

@worker_ready.connect
def check_redis_connection(**kwargs):
    """Check Redis connection on worker startup"""
    try:
        redis_client = redis.Redis.from_url('redis://redis:6379/0')
        redis_client.ping()
        logger.debug("Successfully connected to Redis")
    except redis.ConnectionError:
        logger.error("Cannot connect to Redis! Celery worker will not function properly.")