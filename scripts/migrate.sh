#!/bin/bash
# Run database migrations before starting the application
set -e

echo "Running database migrations..."

python -c "
import asyncio
from app.memory.long_term import db
from app.migrations.runner import run_pending_migrations

async def migrate():
    await db.connect()
    try:
        await run_pending_migrations()
    finally:
        await db.disconnect()

asyncio.run(migrate())
"

echo "Migrations complete."
