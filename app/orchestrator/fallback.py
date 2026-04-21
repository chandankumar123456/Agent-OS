from typing import Dict, Any, List, Optional


class FallbackAgent:
    def __init__(self, primary_agent: str, fallback_agent: str):
        self.primary_agent = primary_agent
        self.fallback_agent = fallback_agent
        self.fallback_count = 0
        self.max_fallbacks = 3
    
    async def execute_with_fallback(
        self,
        primary_func,
        fallback_func,
        *args,
        **kwargs
    ) -> Any:
        try:
            result = await primary_func(*args, **kwargs)
            return result
        except Exception as e:
            self.fallback_count += 1
            
            if self.fallback_count <= self.max_fallbacks:
                return await fallback_func(*args, **kwargs)
            else:
                raise e
    
    def reset(self):
        self.fallback_count = 0


class FallbackManager:
    def __init__(self):
        self.fallbacks: Dict[str, FallbackAgent] = {}
    
    def register_fallback(
        self,
        primary_agent: str,
        fallback_agent: str
    ):
        self.fallbacks[primary_agent] = FallbackAgent(primary_agent, fallback_agent)
    
    def get_fallback(self, agent_name: str) -> Optional[FallbackAgent]:
        return self.fallbacks.get(agent_name)
    
    def reset_all(self):
        for fallback in self.fallbacks.values():
            fallback.reset()


fallback_manager = FallbackManager()