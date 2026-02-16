#!/bin/bash
# Docker entrypoint script for HPC Drive
# Automatically runs migrations before starting the server

set -e

echo "🚀 Starting HPC Drive Service..."

# Run database migrations
echo "📦 Running database migrations..."
cd /app
alembic upgrade head

echo "✅ Migrations completed!"

# Start the FastAPI server
echo "🌐 Starting FastAPI server..."
exec uvicorn --app-dir src hpc_drive.main:app --host 0.0.0.0 --port 7777
