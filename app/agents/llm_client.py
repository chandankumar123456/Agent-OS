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
        if not self.api_key:
            raise RuntimeError("OpenAI API key is required")

        self.client = AsyncOpenAI(api_key=self.api_key)
        logger.info(f"LLM client initialized with model: {self.model}")

    async def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("LLM returned empty content (possible content filter or refusal)")
            return content
        except Exception as e:
            logger.error(f"LLM completion failed: {e}")
            raise

    async def complete_json(
        self,
        messages: List[Dict[str, str]],
        response_schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        import json
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            }
            if response_schema:
                # OpenAI structured output support (o1/gpt-4o and later)
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response",
                        "schema": response_schema,
                        "strict": True,
                    },
                }
            response = await self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("LLM returned empty content (possible content filter or refusal)")
            return json.loads(content)
        except Exception as e:
            logger.error(f"LLM JSON completion failed: {e}")
            raise


# Deferred singleton - import-time safe
_llm_client_instance: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client_instance
    if _llm_client_instance is None:
        _llm_client_instance = LLMClient()
    return _llm_client_instance
