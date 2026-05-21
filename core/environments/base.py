from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseEnvironment(ABC):
    name: str = "base"

    @abstractmethod
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, str]:
        pass
