from abc import ABC, abstractmethod
from typing import List, Optional
import httpx

from ...config.settings import settings
from ...logs.logger import logger
from .schemas import ChatMessage, ChatResponse


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        ...


class OpenAIProvider(LLMProvider):
    def __init__(self):
        self.name = "openai"
        try:
            from openai import AsyncOpenAI

            self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            self.client = None

    async def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        if not self.client:
            return ChatResponse(
                content="[OpenAI client not initialized]",
                model=model or "unknown",
            )
        try:
            kwargs = {
                "model": model or settings.OPENAI_MODEL,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": temperature,
            }
            if max_tokens is not None:
                if kwargs["model"].startswith(("o1", "o3")) or "gpt-5" in kwargs["model"]:
                    kwargs["max_completion_tokens"] = max_tokens
                else:
                    kwargs["max_tokens"] = max_tokens
            resp = await self.client.chat.completions.create(**kwargs)
            choice = resp.choices[0]
            return ChatResponse(
                content=choice.message.content or "",
                model=resp.model,
                input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
                output_tokens=resp.usage.completion_tokens if resp.usage else 0,
                finish_reason=choice.finish_reason,
            )
        except Exception as e:
            logger.error(f"OpenAI chat failed: {e}")
            raise


class AnthropicProvider(LLMProvider):
    def __init__(self):
        self.name = "anthropic"
        try:
            import anthropic

            self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            self._available = True
        except Exception as e:
            logger.warning(f"Anthropic SDK not available: {e}")
            self.client = None
            self._available = False

    async def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        if not self._available:
            return ChatResponse(
                content=f"[Anthropic mock response for model {model or 'claude-3-5-sonnet'}]",
                model=model or "claude-3-5-sonnet",
                input_tokens=0,
                output_tokens=0,
                finish_reason="stop",
            )
        try:
            system = None
            chat_messages = []
            for m in messages:
                if m.role == "system":
                    system = m.content
                else:
                    chat_messages.append({"role": m.role, "content": m.content})
            kwargs = {
                "model": model or "claude-3-5-sonnet-20241022",
                "messages": chat_messages,
                "max_tokens": max_tokens or 2048,
            }
            if system:
                kwargs["system"] = system
            if temperature is not None:
                kwargs["temperature"] = temperature
            resp = await self.client.messages.create(**kwargs)
            return ChatResponse(
                content=resp.content[0].text if resp.content else "",
                model=resp.model,
                input_tokens=resp.usage.input_tokens if resp.usage else 0,
                output_tokens=resp.usage.output_tokens if resp.usage else 0,
                finish_reason=resp.stop_reason,
            )
        except Exception as e:
            logger.error(f"Anthropic chat failed: {e}")
            raise


class GoogleProvider(LLMProvider):
    def __init__(self):
        self.name = "google"
        try:
            import google.generativeai as genai

            genai.configure(api_key=settings.GOOGLE_API_KEY)
            self.client = genai
            self._available = True
        except Exception as e:
            logger.warning(f"Google Generative AI SDK not available: {e}")
            self.client = None
            self._available = False

    async def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        if not self._available:
            return ChatResponse(
                content=f"[Google mock response for model {model or 'gemini-pro'}]",
                model=model or "gemini-pro",
                input_tokens=0,
                output_tokens=0,
                finish_reason="stop",
            )
        try:
            import asyncio

            model_name = model or "gemini-1.5-flash"
            gen_model = self.client.GenerativeModel(model_name)
            prompt = "\n".join([f"{m.role}: {m.content}" for m in messages])
            response = await asyncio.to_thread(gen_model.generate_content, prompt)
            text = response.text if hasattr(response, "text") else str(response)
            return ChatResponse(
                content=text,
                model=model_name,
                input_tokens=0,
                output_tokens=0,
                finish_reason="stop",
            )
        except Exception as e:
            logger.error(f"Google chat failed: {e}")
            raise


class OllamaProvider(LLMProvider):
    def __init__(self):
        self.name = "ollama"
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.client = httpx.AsyncClient(timeout=120.0)

    async def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        try:
            payload = {
                "model": model or "llama3",
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "stream": False,
                "options": {},
            }
            if temperature is not None:
                payload["options"]["temperature"] = temperature
            if max_tokens is not None:
                payload["options"]["num_predict"] = max_tokens
            resp = await self.client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            return ChatResponse(
                content=content,
                model=model or "llama3",
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
                finish_reason="stop",
            )
        except Exception as e:
            logger.error(f"Ollama chat failed: {e}")
            return ChatResponse(
                content=f"[Ollama mock response for model {model or 'llama3'}]",
                model=model or "llama3",
                input_tokens=0,
                output_tokens=0,
                finish_reason="stop",
            )
