"""LocalLogger — structured JSON logging to rotating files for desktop-native mode.

Replaces stdout-only logging with file-based rotating logs:
- Structured JSON format for machine parsing
- Log rotation (10MB x 5 files)
- Separate log levels for file vs console
- Desktop-native: no external dependencies

Usage:
    from core.desktop_native.local_logger import local_logger
    local_logger.info("Task started", task_id="123", extra={"query": "hello"})
"""

import json
import logging
import os
import sys
import gzip
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from logging.handlers import RotatingFileHandler


class _AgentOSJsonFormatter(logging.Formatter):
    """JSON formatter that outputs structured log records."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "task_id") and record.task_id:
            log_obj["task_id"] = record.task_id
        if hasattr(record, "extra_data") and record.extra_data:
            log_obj["data"] = record.extra_data
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, default=str)


class LocalLogger:
    """Desktop-native logger with rotating file output and optional console output."""

    def __init__(
        self,
        name: str = "agent-os",
        log_dir: Optional[str] = None,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
        file_level: int = logging.DEBUG,
        console_level: int = logging.INFO,
    ):
        self.name = name
        self._log_dir = log_dir or os.path.join(Path.home(), ".agentos", "logs")
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._file_level = file_level
        self._console_level = console_level
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.DEBUG)
        self._initialized = False

    def _ensure_dir(self):
        Path(self._log_dir).mkdir(parents=True, exist_ok=True)

    def initialize(self):
        """Initialize handlers. Idempotent."""
        if self._initialized:
            return

        self._ensure_dir()

        # Clear existing handlers to avoid duplicates
        self._logger.handlers = []

        # File handler with JSON formatting
        log_path = os.path.join(self._log_dir, "agentos.log")
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=self._max_bytes,
            backupCount=self._backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(self._file_level)
        file_handler.setFormatter(_AgentOSJsonFormatter())
        self._logger.addHandler(file_handler)

        # Console handler with plain text formatting
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self._console_level)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        self._logger.addHandler(console_handler)

        self._initialized = True
        self.info("LocalLogger initialized", extra={"log_dir": self._log_dir})

    def _log(self, level: int, message: str, task_id: Optional[str] = None, extra: Optional[Dict[str, Any]] = None):
        if not self._initialized:
            self.initialize()

        extra_attrs = {"task_id": task_id, "extra_data": extra or {}}
        self._logger.log(level, message, extra=extra_attrs)

    def debug(self, message: str, task_id: Optional[str] = None, extra: Optional[Dict[str, Any]] = None):
        self._log(logging.DEBUG, message, task_id, extra)

    def info(self, message: str, task_id: Optional[str] = None, extra: Optional[Dict[str, Any]] = None):
        self._log(logging.INFO, message, task_id, extra)

    def warning(self, message: str, task_id: Optional[str] = None, extra: Optional[Dict[str, Any]] = None):
        self._log(logging.WARNING, message, task_id, extra)

    def error(self, message: str, task_id: Optional[str] = None, extra: Optional[Dict[str, Any]] = None):
        self._log(logging.ERROR, message, task_id, extra)

    def critical(self, message: str, task_id: Optional[str] = None, extra: Optional[Dict[str, Any]] = None):
        self._log(logging.CRITICAL, message, task_id, extra)

    def log_task(self, task_id: str, status: str, **kwargs: Any):
        self.info("task_lifecycle", task_id=task_id, extra={"status": status, **kwargs})

    def log_tool(self, tool_name: str, task_id: str, status: str, **kwargs: Any):
        self.info("tool_execution", task_id=task_id, extra={"tool": tool_name, "status": status, **kwargs})

    def log_error(self, exc: Exception, task_id: Optional[str] = None, **kwargs: Any):
        error_detail = {
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            **kwargs,
        }
        self.error(f"exception: {type(exc).__name__}", task_id=task_id, extra=error_detail)

    def get_log_files(self) -> list:
        """Return list of log file paths."""
        log_dir = Path(self._log_dir)
        return sorted(log_dir.glob("agentos.log*"))

    def rotate(self):
        """Force log rotation."""
        for handler in self._logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                handler.doRollover()


# Module-level singleton
local_logger = LocalLogger()
