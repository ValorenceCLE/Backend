#!/bin/sh

# Ensure generate_certs.sh is executable even if host volume overwrote permissions
chmod +x /app/scripts/generate_certs.sh

# Run cert generation
/app/scripts/generate_certs.sh

# Start backend app
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
