from celery import Celery

# Create Celery instance
app = Celery(
    'backend',
    broker='redis://redis:6379/0',
    backend='redis://redis:6379/0',
    include=['celery_app.tasks']
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
            'task': 'celery_app.tasks.read_all_sensors',
            'schedule': 5.0,
        },
    }
)