#!/bin/bash
# Alembic Upgrade Script
# This script applies all pending migrations

cd "$(dirname "$0")"

echo "=== Applying Alembic Migrations ==="

# Apply migrations
alembic upgrade head

echo ""
echo "=== Migration completed! ==="
echo "Database is now up to date."
