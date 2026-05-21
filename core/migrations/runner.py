"""
Migration runner for AgentOS
Tracks applied migrations and runs pending ones in order.
"""
import re
from pathlib import Path
from typing import List, Tuple

from sqlalchemy import text

from ..memory.long_term import db
from ..logs.logger import logger


MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"
MIGRATION_TABLE = "schema_migrations"


def _is_sqlite() -> bool:
    """Detect if the database backend is SQLite."""
    if db.engine is None:
        return False
    return "sqlite" in str(db.engine.url).lower()


def _is_postgresql() -> bool:
    """Detect if the database backend is PostgreSQL."""
    if db.engine is None:
        return False
    return "postgresql" in str(db.engine.url).lower()


async def ensure_migration_table():
    """Create migration tracking table if it doesn't exist.

    Uses backend-appropriate DDL: PostgreSQL TIMESTAMP WITHOUT TIME ZONE
    vs SQLite TEXT with datetime() default.
    """
    async with db.engine.begin() as conn:
        if _is_postgresql():
            await conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
                    version INTEGER PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    applied_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                )
            """))
        else:
            # SQLite and other backends
            await conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
                    version INTEGER PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    applied_at TEXT DEFAULT (datetime('now'))
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

    Uses a simple state machine to avoid splitting on semicolons
    inside string literals.
    """
    statements = []
    current = []
    in_string = False
    string_char = None

    for line in sql.split("\n"):
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue

        i = 0
        while i < len(line):
            ch = line[i]
            if not in_string and ch in ("'", '"'):
                in_string = True
                string_char = ch
            elif in_string and ch == string_char:
                # Check for escaped quote
                if i + 1 < len(line) and line[i + 1] == string_char:
                    i += 1
                else:
                    in_string = False
                    string_char = None
            current.append(ch)
            i += 1
        current.append("\n")

        if not in_string and stripped.endswith(";"):
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []

    if current:
        stmt = "".join(current).strip()
        if stmt and not stmt.startswith("--"):
            statements.append(stmt)

    return statements


def _translate_for_sqlite(sql: str) -> str:
    """Translate PostgreSQL DDL to SQLite-compatible DDL.

    Handles the most common PostgreSQL->SQLite syntax differences.
    Returns None for statements that should be skipped entirely.

    Supported translations:
    - TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() → TEXT DEFAULT (datetime('now'))
    - UUID PRIMARY KEY DEFAULT gen_random_uuid() → TEXT PRIMARY KEY
    - ALTER TABLE t ADD COLUMN IF NOT EXISTS c → ALTER TABLE t ADD COLUMN c
    - BOOLEAN → INTEGER / DOUBLE PRECISION → REAL / etc.
    """
    translated = sql

    # Skip ALTER COLUMN TYPE statements (SQLite doesn't support them)
    if re.search(r'ALTER\s+TABLE\s+\S+\s+ALTER\s+COLUMN', translated, re.IGNORECASE):
        return None  # Signal to skip

    # ALTER TABLE t ADD COLUMN IF NOT EXISTS → ALTER TABLE t ADD COLUMN
    # SQLite doesn't support IF NOT EXISTS in ALTER TABLE
    translated = re.sub(
        r'ALTER\s+TABLE\s+(\S+)\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS',
        r'ALTER TABLE \1 ADD COLUMN',
        translated, flags=re.IGNORECASE
    )

    # Replace PostgreSQL-specific types with SQLite equivalents
    replacements = [
        # TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() → TEXT DEFAULT (datetime('now'))
        (r'TIMESTAMP\s+WITHOUT\s+TIME\s+ZONE\s+DEFAULT\s+NOW\(\)', r"TEXT DEFAULT (datetime('now'))", re.IGNORECASE),
        # TIMESTAMP WITHOUT TIME ZONE → TEXT
        (r'TIMESTAMP\s+WITHOUT\s+TIME\s+ZONE', 'TEXT', re.IGNORECASE),
        # DEFAULT NOW() → DEFAULT (datetime('now'))  (for non-timestamp contexts)
        (r'DEFAULT\s+NOW\(\)', r"DEFAULT (datetime('now'))", re.IGNORECASE),
        # UUID PRIMARY KEY DEFAULT gen_random_uuid() → TEXT PRIMARY KEY
        (r'UUID\s+PRIMARY\s+KEY\s+DEFAULT\s+gen_random_uuid\(\)', 'TEXT PRIMARY KEY', re.IGNORECASE),
        # id UUID → id TEXT (standalone UUID type)
        (r'\bUUID\b', 'TEXT', re.IGNORECASE),
        # DOUBLE PRECISION → REAL
        (r'DOUBLE\s+PRECISION', 'REAL', re.IGNORECASE),
        # SERIAL → INTEGER
        (r'\bSERIAL\b', 'INTEGER', re.IGNORECASE),
        # JSONB → TEXT
        (r'\bJSONB\b', 'TEXT', re.IGNORECASE),
        # BOOLEAN → INTEGER (SQLite has no real boolean)
        # Keep BOOLEAN — SQLite treats it as NUMERIC affinity
    ]

    for pattern, replacement, flags in replacements:
        translated = re.sub(pattern, replacement, translated, flags=flags)

    return translated


_SKIP_ERROR_PATTERNS = [
    # SQLite: column already exists (ALTER TABLE ADD COLUMN without IF NOT EXISTS)
    "duplicate column name",
    # SQLite: no such column (referenced column from a skipped ALTER)
    "no such column",
    # General SQLite: syntax errors from untranslatable SQL
    "syntax error",
    # SQLite: constraint violations on re-runs
    "already exists",
    # SQLite: near ... syntax error
    "near \"",
    # General operational errors
    "cannot add a column with non-constant default",  # SQLite limitation
]


def _is_skippable_sqlite_error(error_msg: str) -> bool:
    """Check if a SQLite error is safe to skip (non-critical for bootstrap)."""
    msg_lower = str(error_msg).lower()
    return any(pattern in msg_lower for pattern in _SKIP_ERROR_PATTERNS)


async def run_migration(version: int, name: str, filepath: Path):
    """Run a single migration file.

    Translates PostgreSQL-specific DDL to SQLite-compatible syntax
    when the backend is SQLite. Non-critical SQLite errors are logged
    as warnings and skipped to allow bootstrap to proceed.
    """
    sql = filepath.read_text()
    statements = split_sql_statements(sql)

    skipped_count = 0
    async with db.engine.begin() as conn:
        for stmt in statements:
            executable_sql = stmt
            if _is_sqlite():
                translated = _translate_for_sqlite(stmt)
                if translated is None:
                    logger.warning(
                        f"  Skipping untranslatable statement in migration "
                        f"{version:03d}: {stmt[:80].strip()}..."
                    )
                    skipped_count += 1
                    continue
                executable_sql = translated

            try:
                await conn.execute(text(executable_sql))
            except Exception as e:
                error_msg = str(e)
                if _is_sqlite() and _is_skippable_sqlite_error(error_msg):
                    logger.warning(
                        f"  Skipping statement in migration "
                        f"{version:03d} (SQLite compat): {stmt[:80].strip()}... "
                        f"[{type(e).__name__}: {error_msg[:100]}]"
                    )
                    skipped_count += 1
                    continue
                # Re-raise critical errors
                logger.error(
                    f"  Fatal error in migration {version:03d}: "
                    f"{type(e).__name__}: {error_msg[:200]}"
                )
                raise

        # Record migration as applied (use backend-appropriate upsert)
        if _is_postgresql():
            await conn.execute(text(
                f"INSERT INTO {MIGRATION_TABLE} (version, name) VALUES (:version, :name)"
                f" ON CONFLICT (version) DO NOTHING"
            ), {"version": version, "name": name})
        else:
            await conn.execute(text(
                f"INSERT OR IGNORE INTO {MIGRATION_TABLE} (version, name) VALUES (:version, :name)"
            ), {"version": version, "name": name})

    if skipped_count > 0:
        print(f"  Applied migration {version:03d}: {name} ({skipped_count} statement(s) skipped for SQLite compatibility)")
    else:
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
