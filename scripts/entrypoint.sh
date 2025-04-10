#!/bin/sh

# Set proper production settings for uvicorn
WORKERS=$(nproc)
if [ "$WORKERS" -gt 1 ]; then
    WORKERS=$((WORKERS * 2 + 1))
else
    WORKERS=4
fi

# Start backend app with SSL
if [ -f "/app/certs/deviceCert.crt" ] && [ -f "/app/certs/deviceCert.key" ]; then
    echo "Starting FastAPI with SSL using $WORKERS workers"
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
         --workers $WORKERS \
         --ssl-keyfile /app/certs/deviceCert.key \
         --ssl-certfile /app/certs/deviceCert.crt
else
    echo "Starting FastAPI without SSL (certificates not found)"
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
         --workers $WORKERS
fi