import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _is_desktop_mode() -> bool:
    mode = os.environ.get("AGENTOS_RUNTIME_MODE", os.environ.get("RUNTIME_MODE", "http"))
    return mode.lower() == "grpc"


class AgentOSLogEncoder(json.JSONEncoder):
    """JSON encoder that safely handles non-serializable objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Exception):
            return {"type": type(obj).__name__, "message": str(obj)}
        if hasattr(obj, "__dict__"):
            return str(obj)
        return super().default(obj)


class AgentOSLogger:
    """Structured logger for AgentOS. Supports both text and JSON output formats.

    Set AGENTOS_LOG_JSON=1 to enable structured JSON logging.
    Set AGENTOS_LOG_STDERR=1 to write logs to stderr (MCP stdio safety).

    In desktop mode (RUNTIME_MODE=grpc), automatically uses LocalLogger
    with rotating file output in addition to console output.
    """

    def __init__(self, name: str = "agent-os"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        self._json_mode = os.environ.get("AGENTOS_LOG_JSON", "").lower() in ("1", "true", "yes")
        self._desktop_mode = _is_desktop_mode()
        self._local_logger = None

        if self._desktop_mode:
            # In desktop mode, try to use LocalLogger for file output
            try:
                from ..desktop_native.local_logger import LocalLogger
                self._local_logger = LocalLogger(name=name)
                self._local_logger.initialize()
            except Exception as e:
                # Fallback to console-only if LocalLogger fails
                print(f"LocalLogger initialization failed: {e}", file=sys.stderr)

        if not self.logger.handlers:
            stream = sys.stderr if os.environ.get("AGENTOS_LOG_STDERR") else sys.stdout
            handler = logging.StreamHandler(stream)
            handler.setLevel(logging.INFO)
            if hasattr(handler.stream, "reconfigure"):
                handler.stream.reconfigure(encoding="utf-8", errors="replace")
            elif hasattr(handler.stream, "buffer"):
                import io
                handler.stream = io.TextIOWrapper(
                    handler.stream.buffer, encoding="utf-8", errors="replace", line_buffering=True
                )
            if self._json_mode:
                formatter = logging.Formatter('%(message)s')
            else:
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _format(self, level: str, message: str, task_id: Optional[str] = None, **kwargs: Any) -> str:
        if self._json_mode:
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "message": message,
            }
            if task_id:
                record["task_id"] = task_id
            if kwargs:
                record["data"] = kwargs
            return json.dumps(record, cls=AgentOSLogEncoder)
        else:
            parts = [f"{k}={v}" for k, v in kwargs.items()]
            if task_id:
                parts.insert(0, f"task_id={task_id}")
            extra = " ".join(parts)
            return f"{message} {extra}".strip()

    def _maybe_local_log(self, level: str, message: str, task_id: Optional[str] = None, **kwargs: Any):
        """Also log to LocalLogger if in desktop mode."""
        if self._local_logger:
            method = getattr(self._local_logger, level.lower(), None)
            if method:
                try:
                    method(message, task_id=task_id, extra=kwargs)
                except Exception:
                    pass

    def info(self, message: str, task_id: Optional[str] = None, **kwargs: Any) -> None:
        self.logger.info(self._format("INFO", message, task_id, **kwargs))
        self._maybe_local_log("info", message, task_id, **kwargs)

    def error(self, message: str, task_id: Optional[str] = None, **kwargs: Any) -> None:
        self.logger.error(self._format("ERROR", message, task_id, **kwargs))
        self._maybe_local_log("error", message, task_id, **kwargs)

    def debug(self, message: str, task_id: Optional[str] = None, **kwargs: Any) -> None:
        self.logger.debug(self._format("DEBUG", message, task_id, **kwargs))
        self._maybe_local_log("debug", message, task_id, **kwargs)

    def warning(self, message: str, task_id: Optional[str] = None, **kwargs: Any) -> None:
        self.logger.warning(self._format("WARNING", message, task_id, **kwargs))
        self._maybe_local_log("warning", message, task_id, **kwargs)

    def critical(self, message: str, task_id: Optional[str] = None, **kwargs: Any) -> None:
        self.logger.critical(self._format("CRITICAL", message, task_id, **kwargs))
        self._maybe_local_log("critical", message, task_id, **kwargs)

    def log_task(self, task_id: str, status: str, **kwargs: Any) -> None:
        self.info(f"task_lifecycle", task_id=task_id, status=status, **kwargs)

    def log_step(self, task_id: str, step_id: str, step: str, status: str) -> None:
        self.info("step_lifecycle", task_id=task_id, step_id=step_id, step=step, status=status)

    def log_error(self, exc: Exception, task_id: Optional[str] = None, **kwargs: Any) -> None:
        """Log an exception with structured error detail."""
        error_detail = {
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
        if hasattr(exc, "error_type"):
            error_detail["error_kind"] = str(exc.error_type)
        if hasattr(exc, "code"):
            error_detail["error_code"] = str(exc.code)
        if hasattr(exc, "recoverable"):
            error_detail["recoverable"] = exc.recoverable
        if hasattr(exc, "context"):
            error_detail["context"] = exc.context
        error_detail.update(kwargs)
        self.error(f"exception: {type(exc).__name__}", task_id=task_id, **error_detail)

    def log_node(self, node_name: str, task_id: str, status: str, **kwargs: Any) -> None:
        """Log a LangGraph node execution event."""
        self.info("node_execution", task_id=task_id, node=node_name, status=status, **kwargs)

    def log_tool(self, tool_name: str, task_id: str, status: str, **kwargs: Any) -> None:
        """Log a tool execution event."""
        self.info("tool_execution", task_id=task_id, tool=tool_name, status=status, **kwargs)


logger = AgentOSLogger()