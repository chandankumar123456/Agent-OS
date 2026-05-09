"""API route modules for AgentOS.

This module exports all FastAPI route handlers organized by domain.
"""

from . import tasks
from . import auth
from . import tools
from . import agents
from . import config
from . import workflows
from . import onboarding
from . import analytics
from . import chat
from . import providers
from . import knowledge
from . import events
from . import workspaces
from . import api_keys
from . import deployments
from . import observability
from . import health

__all__ = [
    "tasks",
    "auth",
    "tools",
    "agents",
    "config",
    "workflows",
    "onboarding",
    "analytics",
    "chat",
    "providers",
    "knowledge",
    "events",
    "workspaces",
    "api_keys",
    "deployments",
    "observability",
    "health",
]
