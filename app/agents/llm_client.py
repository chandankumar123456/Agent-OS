from openai import AsyncOpenAI
from typing import Optional, List, Dict, Any
from ..config.settings import settings
from ..logs.logger import logger


class LLMClient:
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        self.model = model or settings.OPENAI_MODEL
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.client = None
        
        if self.api_key and self.api_key != "your-openai-api-key-here":
            self.client = AsyncOpenAI(api_key=self.api_key)
            logger.info(f"LLM client initialized with model: {self.model}")
        else:
            logger.warning("OpenAI API key not configured - using mock mode")
    
    async def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        if not self.client:
            return self._mock_complete(messages)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM completion failed: {e}")
            return self._mock_complete(messages)
    
    async def complete_json(
        self,
        messages: List[Dict[str, str]],
        response_schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self.client:
            return self._mock_complete_json()
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            import json
            return json.loads(content)
        except Exception as e:
            logger.error(f"LLM JSON completion failed: {e}")
            return self._mock_complete_json()
    
    def _mock_complete(self, messages: List[Dict[str, str]]) -> str:
        user_message = next(
            (m["content"] for m in messages if m["role"] == "user"),
            "process this request"
        )
        return f"processed: {user_message}"
    
    def _mock_complete_json(self) -> Dict[str, Any]:
        return {"steps": [{"step": "mock_step", "agent_type": "executor", "depends_on": []}]}


llm_client = LLMClient()
