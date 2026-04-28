"""Stdout sanitization for MCP stdio servers.

Import this module as the VERY FIRST import in any MCP stdio server file.
It ensures that no library code accidentally writes non-JSON text to stdout,
which would corrupt the JSON-RPC transport.

Usage:
    import app.mcp.servers._stdio_sanitize  # noqa: F401  Must be first!
"""
import builtins
import logging
import sys


# Module-level reference to the original print (exposed for tests)
_orig_print = builtins.print


def _apply():
    global _orig_print
    # ── 1. Patch builtins.print to default to stderr ──────────────────
    _orig_print = builtins.print

    def _safe_print(*args, **kwargs):
        kwargs.setdefault("file", sys.stderr)
        return _orig_print(*args, **kwargs)

    builtins.print = _safe_print

    # ── 2. Force root logging to stderr ───────────────────────────────
    # This overrides any basicConfig() that a library may have already run.
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.WARNING,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )

    # Replace any existing stdout handlers on the root logger with stderr
    root = logging.getLogger()
    for handler in list(root.handlers):
        if hasattr(handler, "stream") and handler.stream is sys.stdout:
            handler.stream = sys.stderr

    # Also sweep existing non-root loggers that may have stdout handlers
    for logger_name in list(logging.root.manager.loggerDict.keys()):
        logger = logging.getLogger(logger_name)
        for handler in list(logger.handlers):
            if hasattr(handler, "stream") and handler.stream is sys.stdout:
                handler.stream = sys.stderr

    # ── 3. Suppress noisy third-party libraries ───────────────────────
    _NOISY = (
        "comtypes",
        "comtypes.client",
        "comtypes.client._generate",
        "comtypes.gen",
        "comtypes._meta",
        "httpx",
        "httpcore",
        "openai",
        "urllib3",
        "bs4",
        "playwright",
        "PIL",
        "pdfplumber",
        "docx",
        "pyautogui",
        "uiautomation",
    )
    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)


_apply()
