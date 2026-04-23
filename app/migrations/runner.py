"""
Migration runner for AgentOS
Tracks applied migrations and runs pending ones in order.
"""
import os
import re
from pathlib import Path
from typing import List, Tuple

from sqlalchemy import text

from app.memory.long_term import db


MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"
MIGRATION_TABLE = "schema_migrations"


async def ensure_migration_table():
    """Create migration tracking table if it doesn't exist."""
    async with db.engine.begin() as conn:
        await conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
                version INTEGER PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
            )
        """))


async def get_applied_migrations() -> List[int]:
    """Get list of already applied migration versions."""
    async with db.engine.begin() as conn:
        result = await conn.execute(text(
            f"SELECT version FROM {MIGRATION_TABLE} ORDER BY version"
        ))
        return [row[0] for row in result]


def get_migration_files() -> List[Tuple[int, str, Path]]:
    """Get migration files sorted by version number."""
    if not MIGRATIONS_DIR.exists():
        return []

    migrations = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = re.match(r"(\d+)_", f.name)
        if match:
            version = int(match.group(1))
            migrations.append((version, f.name, f))

    return migrations


def split_sql_statements(sql: str) -> List[str]:
    """Split SQL file into individual statements.
    
    asyncpg doesn't support multiple commands in a prepared statement,
    so we need to execute each statement separately.
    """
    statements = []
    current = []

    for line in sql.split("\n"):
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue

        current.append(line)

        if stripped.endswith(";"):
            stmt = "\n".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []

    if current:
        stmt = "\n".join(current).strip()
        if stmt and not stmt.startswith("--"):
            statements.append(stmt)

    return statements


async def run_migration(version: int, name: str, filepath: Path):
    """Run a single migration file."""
    sql = filepath.read_text()
    statements = split_sql_statements(sql)

    async with db.engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))

        await conn.execute(text(
            f"INSERT INTO {MIGRATION_TABLE} (version, name) VALUES (:version, :name)"
            f" ON CONFLICT (version) DO NOTHING"
        ), {"version": version, "name": name})

    print(f"  Applied migration {version:03d}: {name}")


async def run_pending_migrations():
    """Run all pending migrations in order."""
    await ensure_migration_table()
    applied = await get_applied_migrations()
    migrations = get_migration_files()

    pending = [(v, n, f) for v, n, f in migrations if v not in applied]

    if not pending:
        print("Database schema is up to date.")
        return

    print(f"Applying {len(pending)} pending migration(s)...")
    for version, name, filepath in pending:
        await run_migration(version, name, filepath)

    print("All migrations applied successfully.")


async def get_schema_status() -> dict:
    """Get current schema status for reporting."""
    await ensure_migration_table()
    applied = await get_applied_migrations()
    migrations = get_migration_files()

    return {
        "total_migrations": len(migrations),
        "applied": len(applied),
        "pending": len(migrations) - len(applied),
        "latest_version": max(applied) if applied else 0,
        "migrations": [
            {"version": v, "name": n, "applied": v in applied}
            for v, n, _ in migrations
        ]
    }


if __name__ == "__main__":
    import asyncio

    async def main():
        await db.connect()
        try:
            await run_pending_migrations()
            status = await get_schema_status()
            print(f"\nSchema status: {status['applied']}/{status['total_migrations']} migrations applied")
        finally:
            await db.disconnect()

    asyncio.run(main())
