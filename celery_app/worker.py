# Backend/celery_app/worker.py
from celery_app import app

if __name__ == '__main__':
    app.start()