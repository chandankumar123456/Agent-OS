import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict


class AgentOSLogger:
    def __init__(self, name: str = "agent-os"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            # Use stderr when running as an MCP stdio server to avoid corrupting JSON-RPC
            stream = sys.stderr if os.environ.get("AGENTOS_LOG_STDERR") else sys.stdout
            handler = logging.StreamHandler(stream)
            handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def info(self, message: str, **kwargs: Any) -> None:
        extra = " ".join([f"{k}={v}" for k, v in kwargs.items()])
        self.logger.info(f"{message} {extra}".strip())
    
    def error(self, message: str, **kwargs: Any) -> None:
        extra = " ".join([f"{k}={v}" for k, v in kwargs.items()])
        self.logger.error(f"{message} {extra}".strip())
    
    def debug(self, message: str, **kwargs: Any) -> None:
        extra = " ".join([f"{k}={v}" for k, v in kwargs.items()])
        self.logger.debug(f"{message} {extra}".strip())
    
    def warning(self, message: str, **kwargs: Any) -> None:
        extra = " ".join([f"{k}={v}" for k, v in kwargs.items()])
        self.logger.warning(f"{message} {extra}".strip())
    
    def log_task(self, task_id: str, status: str, **kwargs: Any) -> None:
        self.info(f"task_id={task_id} status={status}", **kwargs)
    
    def log_step(self, task_id: str, step_id: str, step: str, status: str) -> None:
        self.info(f"task_id={task_id} step_id={step_id} step={step} status={status}")


logger = AgentOSLogger()