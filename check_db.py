import asyncio
from app.memory.long_term import db
from sqlalchemy import text


async def check():
    await db.connect()
    async with db.engine.connect() as conn:
        print("=== TASKS TABLE COLUMNS ===")
        result = await conn.execute(text(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'tasks'
            ORDER BY ordinal_position
            """
        ))
        for row in result:
            print(f"  {row[0]}: {row[1]} (nullable={row[2]}, default={row[3]})")

        print("\n=== TASKS TABLE INDEXES ===")
        result = await conn.execute(text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'tasks'
            ORDER BY indexname
            """
        ))
        for row in result:
            print(f"  {row[0]}: {row[1]}")

        print("\n=== WORKFLOWS TABLE COLUMNS ===")
        result = await conn.execute(text(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'workflows'
            ORDER BY ordinal_position
            """
        ))
        for row in result:
            print(f"  {row[0]}: {row[1]} (nullable={row[2]}, default={row[3]})")

        print("\n=== TRACES TABLE COLUMNS ===")
        result = await conn.execute(text(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'traces'
            ORDER BY ordinal_position
            """
        ))
        for row in result:
            print(f"  {row[0]}: {row[1]} (nullable={row[2]}, default={row[3]})")

        print("\n=== NODE_TRACES TABLE COLUMNS ===")
        result = await conn.execute(text(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'node_traces'
            ORDER BY ordinal_position
            """
        ))
        for row in result:
            print(f"  {row[0]}: {row[1]} (nullable={row[2]}, default={row[3]})")

        print("\n=== NULL user_id CHECK ===")
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM tasks WHERE user_id IS NULL"
        ))
        null_count = result.scalar()
        print(f"  Tasks with NULL user_id: {null_count}")

        result = await conn.execute(text(
            "SELECT COUNT(*) FROM workflows WHERE user_id IS NULL"
        ))
        null_count = result.scalar()
        print(f"  Workflows with NULL user_id: {null_count}")

    await db.disconnect()


asyncio.run(check())
