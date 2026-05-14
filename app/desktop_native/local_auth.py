"""LocalAuth — desktop-native authentication using OS identity and local secrets.

Replaces JWT/API key validation in desktop mode with:
- OS user identity verification (whoami)
- Local API key stored in SQLite (encrypted with OS keychain/DPAPI)
- No network-based auth required

Security model:
- On Windows: uses DPAPI (Data Protection API) to encrypt local keys
- On macOS: uses Keychain (via keyring library if available)
- On Linux: uses Secret Service / keyring
- Fallback: plain SQLite storage (not recommended for production)
"""

import os
import sys
import hashlib
import secrets
import getpass
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from ..logs.logger import logger
from .sqlite_store import sqlite_store


class LocalAuth:
    """Desktop-native authentication using OS identity and local secrets."""

    def __init__(self):
        self._current_user = getpass.getuser()
        self._machine_id = self._get_machine_id()
        self._using_sqlite = False
        try:
            self._sqlite = sqlite_store
            self._using_sqlite = True
        except Exception:
            self._sqlite = None

    def _get_machine_id(self) -> str:
        """Get a stable machine identifier."""
        # Use environment variable if set, otherwise use hostname
        machine_id = os.environ.get("AGENTOS_MACHINE_ID", "")
        if not machine_id:
            try:
                import socket
                machine_id = socket.gethostname()
            except Exception:
                machine_id = "unknown"
        return machine_id

    async def _ensure_table(self):
        if not self._using_sqlite:
            return
        try:
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS local_auth (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_name TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    api_key_hash TEXT NOT NULL,
                    api_key_encrypted TEXT,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
            """)
            await self._sqlite.commit()
        except Exception as e:
            logger.warning(f"Failed to create local_auth table: {e}")

    async def initialize(self) -> str:
        """Initialize local auth and generate a secure API key.

        Returns:
            The generated API key (store this securely).
        """
        await self._ensure_table()

        # Check if already initialized
        existing = await self.get_active_key()
        if existing:
            logger.info("LocalAuth already initialized")
            return existing

        # Generate a secure API key
        api_key = "aos_" + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # Try to encrypt with OS-level protection
        encrypted = self._encrypt_key(api_key)

        now = datetime.now(timezone.utc).isoformat()
        if self._using_sqlite:
            await self._sqlite.execute(
                """
                INSERT INTO local_auth (user_name, machine_id, api_key_hash, api_key_encrypted, created_at, last_used_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (self._current_user, self._machine_id, key_hash, encrypted, now, now),
            )
            await self._sqlite.commit()

        logger.info(f"LocalAuth initialized for user {self._current_user} on {self._machine_id}")
        return api_key

    async def validate_key(self, api_key: str) -> bool:
        """Validate a local API key."""
        if not api_key or not api_key.startswith("aos_"):
            return False

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        if self._using_sqlite:
            try:
                await self._ensure_table()
                row = await self._sqlite.fetchone(
                    "SELECT * FROM local_auth WHERE api_key_hash = ? AND is_active = 1",
                    (key_hash,),
                )
                if row:
                    # Update last_used_at
                    now = datetime.now(timezone.utc).isoformat()
                    await self._sqlite.execute(
                        "UPDATE local_auth SET last_used_at = ? WHERE api_key_hash = ?",
                        (now, key_hash),
                    )
                    await self._sqlite.commit()
                    return True
            except Exception as e:
                logger.warning(f"Local auth validation error: {e}")

        return False

    async def get_active_key(self) -> Optional[str]:
        """Get the currently active API key hash."""
        if self._using_sqlite:
            try:
                await self._ensure_table()
                row = await self._sqlite.fetchone(
                    "SELECT api_key_hash FROM local_auth WHERE user_name = ? AND machine_id = ? AND is_active = 1 ORDER BY created_at DESC LIMIT 1",
                    (self._current_user, self._machine_id),
                )
                if row:
                    return row["api_key_hash"]
            except Exception as e:
                logger.warning(f"Failed to get active key: {e}")
        return None

    async def revoke_all_keys(self) -> int:
        """Revoke all active keys. Returns count of revoked keys."""
        if self._using_sqlite:
            try:
                await self._ensure_table()
                cursor = await self._sqlite.execute(
                    "UPDATE local_auth SET is_active = 0 WHERE user_name = ? AND machine_id = ?",
                    (self._current_user, self._machine_id),
                )
                await self._sqlite.commit()
                return cursor.rowcount if hasattr(cursor, "rowcount") else 0
            except Exception as e:
                logger.warning(f"Failed to revoke keys: {e}")
        return 0

    def _encrypt_key(self, api_key: str) -> str:
        """Encrypt API key using OS-level protection."""
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                # Use Windows DPAPI via ctypes
                class DATA_BLOB(ctypes.Structure):
                    _fields_ = [
                        ("cbData", wintypes.DWORD),
                        ("pbData", wintypes.LPBYTE),
                    ]

                CRYPTPROTECT_UI_FORBIDDEN = 0x01

                data_in = DATA_BLOB()
                data_in.cbData = len(api_key.encode())
                data_in.pbData = ctypes.cast(api_key.encode(), wintypes.LPBYTE)

                data_out = DATA_BLOB()

                if ctypes.windll.crypt32.CryptProtectData(
                    ctypes.byref(data_in),
                    None,
                    None,
                    None,
                    None,
                    CRYPTPROTECT_UI_FORBIDDEN,
                    ctypes.byref(data_out),
                ):
                    encrypted_bytes = ctypes.string_at(data_out.pbData, data_out.cbData)
                    ctypes.windll.kernel32.LocalFree(data_out.pbData)
                    return "dpapi:" + encrypted_bytes.hex()
                else:
                    logger.warning("DPAPI encryption failed, using plaintext fallback")
            except Exception as e:
                logger.warning(f"Windows DPAPI not available: {e}")

        elif sys.platform == "darwin":
            try:
                import keyring
                keyring.set_password("agentos", "local_api_key", api_key)
                return "keyring:darwin"
            except Exception as e:
                logger.warning(f"macOS keyring not available: {e}")

        else:
            try:
                import keyring
                keyring.set_password("agentos", "local_api_key", api_key)
                return "keyring:linux"
            except Exception as e:
                logger.warning(f"Linux keyring not available: {e}")

        # Fallback: plaintext (not recommended)
        return "plain:" + api_key

    def get_current_identity(self) -> Dict[str, Any]:
        """Get the current OS identity for audit logging."""
        return {
            "user_name": self._current_user,
            "machine_id": self._machine_id,
            "platform": sys.platform,
            "pid": os.getpid(),
        }

    async def is_authorized(self, required_role: str = "user") -> bool:
        """Check if current OS user is authorized.

        In desktop mode, we trust the OS user identity.
        Additional roles can be checked against local policy.
        """
        # Always authorized in desktop mode (OS identity is the boundary)
        return True


# Module-level singleton
local_auth = LocalAuth()
