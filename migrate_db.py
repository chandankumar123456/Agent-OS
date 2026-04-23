import asyncio
from app.memory.long_term import db
from sqlalchemy import text


async def migrate():
    await db.connect()
    async with db.engine.connect() as conn:
        await conn.execute(text(
            "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS user_id VARCHAR(36) DEFAULT 'system' NOT NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_tasks_user_id_created_at ON tasks(user_id, created_at DESC)"
        ))
        await conn.commit()
        print("Migration complete: added user_id column and indexes")
    await db.disconnect()


asyncio.run(migrate())
