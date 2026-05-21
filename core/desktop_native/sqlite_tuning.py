"""SQLiteTuning — production SQLite configuration for desktop-native runtime.

Applies optimal pragmas for single-writer, multi-reader desktop use:
- WAL mode for concurrent reads during writes
- Memory-mapped I/O for speed
- Optimized cache size and page size
- Auto-vacuum and integrity check scheduling

Usage:
    from core.desktop_native.sqlite_tuning import sqlite_tuning
    await sqlite_tuning.apply_optimizations()
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional

from ..logs.logger import logger
from .sqlite_store import sqlite_store


class SQLiteTuning:
    """Manages SQLite performance tuning and maintenance."""

    def __init__(self):
        self._sqlite = sqlite_store
        self._last_vacuum: Optional[datetime] = None
        self._last_integrity_check: Optional[datetime] = None

    async def apply_optimizations(self) -> Dict[str, Any]:
        """Apply all recommended SQLite pragmas for desktop-native use.

        Returns:
            Dict with the results of each pragma setting.
        """
        results = {}

        # WAL mode: allows readers to not block writers
        try:
            row = await self._sqlite.fetchone("PRAGMA journal_mode=WAL")
            results["journal_mode"] = row[0] if row else "unknown"
            logger.info(f"SQLite journal_mode set to: {results['journal_mode']}")
        except Exception as e:
            results["journal_mode"] = f"error: {e}"
            logger.warning(f"Failed to set WAL mode: {e}")

        # Synchronous mode: NORMAL is a good balance for WAL
        try:
            await self._sqlite.execute("PRAGMA synchronous=NORMAL")
            row = await self._sqlite.fetchone("PRAGMA synchronous")
            results["synchronous"] = row[0] if row else "unknown"
        except Exception as e:
            results["synchronous"] = f"error: {e}"

        # Cache size: 10000 pages (~40MB with 4KB pages)
        try:
            await self._sqlite.execute("PRAGMA cache_size=-10000")
            row = await self._sqlite.fetchone("PRAGMA cache_size")
            results["cache_size"] = row[0] if row else "unknown"
        except Exception as e:
            results["cache_size"] = f"error: {e}"

        # Page size: 4096 bytes (standard, good for most workloads)
        try:
            await self._sqlite.execute("PRAGMA page_size=4096")
            row = await self._sqlite.fetchone("PRAGMA page_size")
            results["page_size"] = row[0] if row else "unknown"
        except Exception as e:
            results["page_size"] = f"error: {e}"

        # Temp store: memory (faster for temp tables)
        try:
            await self._sqlite.execute("PRAGMA temp_store=MEMORY")
            row = await self._sqlite.fetchone("PRAGMA temp_store")
            results["temp_store"] = row[0] if row else "unknown"
        except Exception as e:
            results["temp_store"] = f"error: {e}"

        # Auto-vacuum: incremental (prevents db bloat without locking)
        try:
            await self._sqlite.execute("PRAGMA auto_vacuum=INCREMENTAL")
            row = await self._sqlite.fetchone("PRAGMA auto_vacuum")
            results["auto_vacuum"] = row[0] if row else "unknown"
        except Exception as e:
            results["auto_vacuum"] = f"error: {e}"

        # Memory-mapped I/O: 2GB max (speeds up reads)
        try:
            await self._sqlite.execute("PRAGMA mmap_size=2147483648")
            row = await self._sqlite.fetchone("PRAGMA mmap_size")
            results["mmap_size"] = row[0] if row else "unknown"
        except Exception as e:
            results["mmap_size"] = f"error: {e}"

        # Foreign keys: enforce referential integrity
        try:
            await self._sqlite.execute("PRAGMA foreign_keys=ON")
            row = await self._sqlite.fetchone("PRAGMA foreign_keys")
            results["foreign_keys"] = row[0] if row else "unknown"
        except Exception as e:
            results["foreign_keys"] = f"error: {e}"

        # Busy timeout: 5 seconds (wait rather than fail on lock)
        try:
            await self._sqlite.execute("PRAGMA busy_timeout=5000")
            row = await self._sqlite.fetchone("PRAGMA busy_timeout")
            results["busy_timeout"] = row[0] if row else "unknown"
        except Exception as e:
            results["busy_timeout"] = f"error: {e}"

        logger.info(f"SQLite tuning applied: {results}")
        return results

    async def get_db_size_mb(self) -> float:
        """Get the current database file size in MB."""
        try:
            import os
            db_path = self._sqlite._db_path
            if db_path and os.path.exists(db_path):
                size_bytes = os.path.getsize(db_path)
                return size_bytes / (1024 * 1024)
        except Exception as e:
            logger.warning(f"Failed to get DB size: {e}")
        return 0.0

    async def vacuum_if_needed(self, threshold_mb: float = 1024.0) -> bool:
        """Run VACUUM if database exceeds threshold size.

        Returns:
            True if VACUUM was run.
        """
        size_mb = await self.get_db_size_mb()
        if size_mb < threshold_mb:
            return False

        logger.info(f"Database size {size_mb:.1f}MB exceeds {threshold_mb}MB, running VACUUM")
        try:
            # WAL checkpoint first
            await self._sqlite.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            # Then vacuum
            await self._sqlite.execute("VACUUM")
            self._last_vacuum = datetime.now(timezone.utc)
            new_size = await self.get_db_size_mb()
            logger.info(f"VACUUM complete: {size_mb:.1f}MB -> {new_size:.1f}MB")
            return True
        except Exception as e:
            logger.error(f"VACUUM failed: {e}")
            return False

    async def run_integrity_check(self) -> Dict[str, Any]:
        """Run PRAGMA integrity_check and return results."""
        try:
            rows = await self._sqlite.fetchall("PRAGMA integrity_check")
            results = [r[0] for r in rows]
            ok = all(r == "ok" for r in results)
            self._last_integrity_check = datetime.now(timezone.utc)
            return {
                "ok": ok,
                "messages": results,
                "checked_at": self._last_integrity_check.isoformat(),
            }
        except Exception as e:
            return {
                "ok": False,
                "messages": [str(e)],
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

    async def get_performance_stats(self) -> Dict[str, Any]:
        """Get SQLite performance and storage statistics."""
        stats = {}

        # Page count
        try:
            row = await self._sqlite.fetchone("PRAGMA page_count")
            stats["page_count"] = row[0] if row else 0
        except Exception:
            stats["page_count"] = 0

        # Freelist count (unused pages)
        try:
            row = await self._sqlite.fetchone("PRAGMA freelist_count")
            stats["freelist_count"] = row[0] if row else 0
        except Exception:
            stats["freelist_count"] = 0

        # Database size
        stats["size_mb"] = await self.get_db_size_mb()

        # WAL file size
        try:
            import os
            wal_path = self._sqlite._db_path + "-wal"
            if os.path.exists(wal_path):
                stats["wal_size_mb"] = os.path.getsize(wal_path) / (1024 * 1024)
            else:
                stats["wal_size_mb"] = 0.0
        except Exception:
            stats["wal_size_mb"] = 0.0

        # Last maintenance
        stats["last_vacuum"] = self._last_vacuum.isoformat() if self._last_vacuum else None
        stats["last_integrity_check"] = self._last_integrity_check.isoformat() if self._last_integrity_check else None

        return stats

    async def maintenance_pass(self) -> Dict[str, Any]:
        """Run a full maintenance pass: checkpoint, vacuum if needed, integrity check.

        Returns:
            Dict with maintenance results.
        """
        results = {
            "checkpoint": False,
            "vacuum": False,
            "integrity_check": {},
            "stats_before": {},
            "stats_after": {},
        }

        results["stats_before"] = await self.get_performance_stats()

        # WAL checkpoint
        try:
            await self._sqlite.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            results["checkpoint"] = True
        except Exception as e:
            logger.warning(f"WAL checkpoint failed: {e}")

        # Vacuum if DB is large
        results["vacuum"] = await self.vacuum_if_needed(threshold_mb=1024.0)

        # Integrity check
        results["integrity_check"] = await self.run_integrity_check()

        results["stats_after"] = await self.get_performance_stats()

        return results


# Module-level singleton
sqlite_tuning = SQLiteTuning()
