#!/bin/bash
# Docker entrypoint script for HPC Drive
# Database tables are auto-created by SQLAlchemy on startup

set -e

echo "🚀 Starting HPC Drive Service..."

# Create data directory if it doesn't exist
mkdir -p /app/data

# Start the FastAPI server (tables auto-created via create_db_and_tables in main.py)
echo "🌐 Starting FastAPI server..."
exec uvicorn --app-dir src hpc_drive.main:app --host 0.0.0.0 --port 7777
