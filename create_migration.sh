#!/bin/bash
# Alembic Migration Script
# This script creates a new migration for the folder_type field

cd "$(dirname "$0")"

echo "=== Creating Alembic Migration ==="

# Create migration
alembic revision --autogenerate -m "Add folder_type field to drive_items"

echo ""
echo "=== Migration file created! ==="
echo "Next step: Run 'alembic upgrade head' to apply the migration"
