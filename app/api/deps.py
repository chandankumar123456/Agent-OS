from typing import Annotated
from fastapi import Depends
from ..orchestrator.core import Orchestrator


def get_orchestrator() -> Orchestrator:
    return Orchestrator()


OrchestratorDep = Annotated[Orchestrator, Depends(get_orchestrator)]