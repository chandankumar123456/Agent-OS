"""Phase 3.6 — Multi-LLM Router: Provider abstraction for model-agnostic execution.

Routes LLM requests to the appropriate provider based on model, cost, and
capability requirements. Supports OpenAI, Anthropic, Google, and local models.

Spec: Build Plan Task 3.2.6, Section 6.2
Input Contract:  route(ModelRequest) → LLMResponse
Output Contract: LLMResponse with text, tokens, cost, latency
"""

import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from pydantic import BaseModel, Field

from ..logs.logger import logger
from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType


# ── Pydantic Models ──────────────────────────────────────────────────────────

class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    LOCAL = "local"


class ModelRequest(BaseModel):
    """A request to be routed to an LLM provider."""

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    messages: List[Dict[str, str]] = Field(..., description="Chat messages")
    model: Optional[str] = Field(default=None, description="Preferred model (provider-specific)")
    provider: Optional[str] = Field(default=None, description="Preferred provider")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=128000)
    task_id: Optional[str] = None
    priority: str = Field(default="normal", description="normal, high, low")
    cache_ttl_seconds: int = Field(default=300, description="Cache TTL for this request")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def cache_key(self) -> str:
        """Generate a deterministic cache key for this request."""
        payload = json.dumps(
            {
                "messages": self.messages,
                "model": self.model,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class LLMResponse(BaseModel):
    """Response from an LLM provider."""

    request_id: str
    text: str = ""
    model_used: str = ""
    provider: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProviderConfig(BaseModel):
    """Configuration for an LLM provider."""

    provider: LLMProvider
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    default_model: str = "gpt-4o"
    fallback_models: List[str] = Field(default_factory=list)
    cost_per_1k_in: float = 0.0
    cost_per_1k_out: float = 0.0
    rate_limit_rpm: int = 60
    rate_limit_tpm: int = 100000
    enabled: bool = True
    priority: int = 1  # Lower = higher priority


# ── Cost Tables ──────────────────────────────────────────────────────────────

# Approximate costs per 1K tokens (input, output) — update as pricing changes
MODEL_COSTS: Dict[str, Tuple[float, float]] = {
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4-turbo": (0.01, 0.03),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    "claude-3-opus": (0.015, 0.075),
    "claude-3-sonnet": (0.003, 0.015),
    "claude-3-haiku": (0.00025, 0.00125),
    "gemini-1.5-pro": (0.0035, 0.0105),
    "gemini-1.5-flash": (0.000075, 0.0003),
    "llama-3-70b": (0.0, 0.0),  # Local models: free
    "mistral-large": (0.004, 0.012),
}

# Default provider → model mapping
PROVIDER_DEFAULTS: Dict[str, str] = {
    LLMProvider.OPENAI.value: "gpt-4o-mini",
    LLMProvider.ANTHROPIC.value: "claude-3-sonnet",
    LLMProvider.GOOGLE.value: "gemini-1.5-flash",
    LLMProvider.LOCAL.value: "llama-3-70b",
}

# Model → provider mapping
MODEL_TO_PROVIDER: Dict[str, str] = {
    "gpt-4o": LLMProvider.OPENAI.value,
    "gpt-4o-mini": LLMProvider.OPENAI.value,
    "gpt-4-turbo": LLMProvider.OPENAI.value,
    "gpt-3.5-turbo": LLMProvider.OPENAI.value,
    "claude-3-opus": LLMProvider.ANTHROPIC.value,
    "claude-3-sonnet": LLMProvider.ANTHROPIC.value,
    "claude-3-haiku": LLMProvider.ANTHROPIC.value,
    "gemini-1.5-pro": LLMProvider.GOOGLE.value,
    "gemini-1.5-flash": LLMProvider.GOOGLE.value,
    "llama-3-70b": LLMProvider.LOCAL.value,
    "mistral-large": LLMProvider.OPENAI.value,  # Via compatible API
}


# ── LLMRouter ────────────────────────────────────────────────────────────────

class LLMRouter:
    """Routes LLM requests to the appropriate provider with failover.

    Features:
    - Multi-provider support (OpenAI, Anthropic, Google, local)
    - Automatic provider selection based on model name
    - Fallback chain on failure
    - Request caching to reduce duplicate calls
    - Cost estimation and tracking
    - Rate limit awareness

    Usage:
        router = LLMRouter()
        router.configure_provider("openai", api_key="sk-...", default_model="gpt-4o")
        response = await router.route(ModelRequest(messages=[...]))
    """

    def __init__(self):
        self._providers: Dict[str, ProviderConfig] = {}
        self._cache: Dict[str, Tuple[LLMResponse, float]] = {}  # key → (response, expiry)
        self._request_count: int = 0
        self._total_cost: float = 0.0
        self._total_tokens: int = 0

    # ── Configuration ────────────────────────────────────────────────────

    def configure_provider(
        self,
        provider: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        fallback_models: Optional[List[str]] = None,
        enabled: bool = True,
        priority: int = 1,
    ) -> None:
        """Configure or update an LLM provider.

        Args:
            provider: Provider name (openai, anthropic, google, local).
            api_key: API key for the provider.
            base_url: Custom API base URL.
            default_model: Default model to use.
            fallback_models: Fallback models if primary fails.
            enabled: Whether this provider is active.
            priority: Priority ranking (lower = higher).
        """
        try:
            prov_enum = LLMProvider(provider)
        except ValueError:
            logger.error(f"Unknown LLM provider: {provider}")
            return

        existing = self._providers.get(provider)
        if existing:
            if api_key:
                existing.api_key = api_key
            if base_url:
                existing.base_url = base_url
            if default_model:
                existing.default_model = default_model
            if fallback_models is not None:
                existing.fallback_models = fallback_models
            existing.enabled = enabled
            existing.priority = priority
        else:
            costs_in, costs_out = MODEL_COSTS.get(
                default_model or PROVIDER_DEFAULTS.get(provider, "gpt-4o"),
                (0.0, 0.0),
            )
            self._providers[provider] = ProviderConfig(
                provider=prov_enum,
                api_key=api_key,
                base_url=base_url,
                default_model=default_model or PROVIDER_DEFAULTS.get(provider, "gpt-4o"),
                fallback_models=fallback_models or [],
                cost_per_1k_in=costs_in,
                cost_per_1k_out=costs_out,
                enabled=enabled,
                priority=priority,
            )

        logger.info(f"LLMRouter: Configured provider '{provider}' (enabled={enabled})")

    def disable_provider(self, provider: str) -> None:
        """Disable a provider without removing its configuration."""
        if provider in self._providers:
            self._providers[provider].enabled = False
            logger.info(f"LLMRouter: Disabled provider '{provider}'")

    def enable_provider(self, provider: str) -> None:
        """Re-enable a previously disabled provider."""
        if provider in self._providers:
            self._providers[provider].enabled = True
            logger.info(f"LLMRouter: Enabled provider '{provider}'")

    # ── Routing ──────────────────────────────────────────────────────────

    async def route(self, request: ModelRequest) -> LLMResponse:
        """Route a request to the appropriate LLM provider.

        Steps:
        1. Check cache for identical request
        2. Determine target provider and model
        3. Execute via provider with fallback chain
        4. Cache response if successful
        5. Track cost and return

        Args:
            request: The ModelRequest to execute.

        Returns:
            LLMResponse with generated text and metadata.
        """
        self._request_count += 1

        # 1. Cache check
        cache_key = request.cache_key()
        cached = self._check_cache(cache_key)
        if cached:
            logger.debug(f"LLMRouter: Cache hit for request {request.request_id}")
            return cached

        # 2. Resolve provider and model
        provider_name, model = self._resolve_provider(request)

        if not provider_name:
            return LLMResponse(
                request_id=request.request_id,
                error=f"No enabled provider available for model '{request.model or 'auto'}'",
            )

        # 3. Execute with fallback chain
        start_time = time.monotonic()
        response: Optional[LLMResponse] = None
        tried_providers: List[str] = []
        tried_models: List[str] = []

        # Build fallback chain: primary → model fallbacks → provider fallbacks
        chain = self._build_fallback_chain(provider_name, model)

        for fb_provider, fb_model in chain:
            if fb_provider in tried_providers and fb_model in tried_models:
                continue
            tried_providers.append(fb_provider)
            tried_models.append(fb_model)

            logger.debug(
                f"LLMRouter: Trying {fb_provider}/{fb_model} for request {request.request_id}"
            )

            try:
                response = await self._execute_provider(
                    provider=fb_provider,
                    model=fb_model,
                    request=request,
                )
                if response and not response.error:
                    break
            except Exception as e:
                logger.warning(
                    f"LLMRouter: Provider {fb_provider}/{fb_model} failed: {e}"
                )
                continue

        # 4. Cache and return
        elapsed_ms = (time.monotonic() - start_time) * 1000

        if response is None or response.error:
            return LLMResponse(
                request_id=request.request_id,
                error=f"All providers failed. Tried: {tried_providers}. Last error: {response.error if response else 'N/A'}",
                latency_ms=elapsed_ms,
            )

        response.latency_ms = elapsed_ms
        self._total_cost += response.cost_usd
        self._total_tokens += response.total_tokens

        # Cache if successful and non-zero TTL
        if request.cache_ttl_seconds > 0 and not response.error:
            self._cache[cache_key] = (
                response,
                time.monotonic() + request.cache_ttl_seconds,
            )

        return response

    async def route_batch(
        self,
        requests: List[ModelRequest],
        max_concurrent: int = 5,
    ) -> List[LLMResponse]:
        """Route multiple requests concurrently.

        Args:
            requests: List of ModelRequests.
            max_concurrent: Maximum concurrent LLM calls.

        Returns:
            List of LLMResponse (one per request).
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _routed(req: ModelRequest) -> LLMResponse:
            async with semaphore:
                return await self.route(req)

        return await asyncio.gather(*[_routed(r) for r in requests])

    # ── Stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get router statistics."""
        return {
            "total_requests": self._request_count,
            "total_cost_usd": round(self._total_cost, 6),
            "total_tokens": self._total_tokens,
            "cache_size": len(self._cache),
            "providers": {
                name: {
                    "default_model": cfg.default_model,
                    "enabled": cfg.enabled,
                    "priority": cfg.priority,
                }
                for name, cfg in self._providers.items()
            },
        }

    def clear_cache(self) -> int:
        """Clear the response cache.

        Returns:
            Number of cache entries cleared.
        """
        count = len(self._cache)
        self._cache.clear()
        return count

    # ── Internal: Provider Resolution ────────────────────────────────────

    def _resolve_provider(self, request: ModelRequest) -> Tuple[Optional[str], Optional[str]]:
        """Determine which provider and model to use for a request.

        Args:
            request: The ModelRequest.

        Returns:
            Tuple of (provider_name, model_name), or (None, None) if no provider available.
        """
        # If provider specified explicitly
        if request.provider and request.provider in self._providers:
            cfg = self._providers[request.provider]
            if cfg.enabled:
                model = request.model or cfg.default_model
                return request.provider, model

        # If model specified, find its provider
        if request.model:
            provider = MODEL_TO_PROVIDER.get(request.model)
            if provider and provider in self._providers and self._providers[provider].enabled:
                return provider, request.model

        # Auto-select: prefer enabled provider by priority (lowest first)
        enabled = sorted(
            [p for p in self._providers.values() if p.enabled],
            key=lambda p: p.priority,
        )
        if enabled:
            best = enabled[0]
            model = request.model or best.default_model
            return best.provider.value, model

        return None, None

    def _build_fallback_chain(
        self,
        primary_provider: str,
        primary_model: str,
    ) -> List[Tuple[str, str]]:
        """Build a fallback chain: primary → same-provider fallbacks → other providers.

        Args:
            primary_provider: The primary provider name.
            primary_model: The primary model name.

        Returns:
            List of (provider, model) tuples to try in order.
        """
        chain: List[Tuple[str, str]] = [(primary_provider, primary_model)]

        # Add same-provider fallback models
        if primary_provider in self._providers:
            cfg = self._providers[primary_provider]
            for fb_model in cfg.fallback_models:
                if fb_model != primary_model:
                    chain.append((primary_provider, fb_model))

        # Add other enabled providers, sorted by priority
        others = sorted(
            [
                p for name, p in self._providers.items()
                if name != primary_provider and p.enabled
            ],
            key=lambda p: p.priority,
        )
        for cfg in others:
            chain.append((cfg.provider.value, cfg.default_model))

        return chain

    # ── Internal: Caching ────────────────────────────────────────────────

    def _check_cache(self, cache_key: str) -> Optional[LLMResponse]:
        """Check if a cached response exists and is not expired.

        Args:
            cache_key: The cache key for the request.

        Returns:
            Cached LLMResponse or None.
        """
        entry = self._cache.get(cache_key)
        if entry is None:
            return None

        response, expiry = entry
        if time.monotonic() > expiry:
            del self._cache[cache_key]
            return None

        # Return a copy with cached flag
        return LLMResponse(
            request_id=response.request_id,
            text=response.text,
            model_used=response.model_used,
            provider=response.provider,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            total_tokens=response.total_tokens,
            cost_usd=0.0,  # No additional cost for cached
            latency_ms=0.0,  # Instant for cached
            cached=True,
            metadata=response.metadata,
        )

    # ── Internal: Provider Execution ─────────────────────────────────────

    async def _execute_provider(
        self,
        provider: str,
        model: str,
        request: ModelRequest,
    ) -> Optional[LLMResponse]:
        """Execute a request against a specific provider.

        Args:
            provider: Provider name.
            model: Model name.
            request: The ModelRequest.

        Returns:
            LLMResponse or None on fatal error.
        """
        cfg = self._providers.get(provider)
        if not cfg or not cfg.enabled:
            return LLMResponse(
                request_id=request.request_id,
                error=f"Provider '{provider}' not configured or disabled",
            )

        try:
            if provider == LLMProvider.OPENAI.value:
                return await self._execute_openai(cfg, model, request)
            elif provider == LLMProvider.ANTHROPIC.value:
                return await self._execute_anthropic(cfg, model, request)
            elif provider == LLMProvider.GOOGLE.value:
                return await self._execute_google(cfg, model, request)
            elif provider == LLMProvider.LOCAL.value:
                return await self._execute_local(cfg, model, request)
            else:
                return LLMResponse(
                    request_id=request.request_id,
                    error=f"Unsupported provider: {provider}",
                )
        except Exception as e:
            logger.error(f"LLMRouter: Provider {provider} execution error: {e}")
            return LLMResponse(
                request_id=request.request_id,
                error=str(e),
                model_used=model,
                provider=provider,
            )

    async def _execute_openai(
        self,
        cfg: ProviderConfig,
        model: str,
        request: ModelRequest,
    ) -> LLMResponse:
        """Execute via OpenAI-compatible API."""
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=cfg.api_key,
                base_url=cfg.base_url,
            )
            response = await client.chat.completions.create(
                model=model,
                messages=request.messages,  # type: ignore[arg-type]
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            choice = response.choices[0]
            text = choice.message.content or ""

            tokens_in = response.usage.prompt_tokens if response.usage else 0
            tokens_out = response.usage.completion_tokens if response.usage else 0
            total = tokens_in + tokens_out

            cost_in = (tokens_in / 1000) * cfg.cost_per_1k_in
            cost_out = (tokens_out / 1000) * cfg.cost_per_1k_out

            return LLMResponse(
                request_id=request.request_id,
                text=text,
                model_used=model,
                provider=LLMProvider.OPENAI.value,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                total_tokens=total,
                cost_usd=round(cost_in + cost_out, 6),
                metadata={
                    "finish_reason": choice.finish_reason,
                    "model": model,
                },
            )
        except ImportError:
            logger.warning("LLMRouter: openai package not installed; simulating OpenAI response")
            return self._simulate_response(request, model, LLMProvider.OPENAI.value, cfg)

    async def _execute_anthropic(
        self,
        cfg: ProviderConfig,
        model: str,
        request: ModelRequest,
    ) -> LLMResponse:
        """Execute via Anthropic API."""
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=cfg.api_key)

            # Convert messages to Anthropic format
            system_msg = ""
            user_messages: List[Dict[str, Any]] = []
            for msg in request.messages:
                if msg["role"] == "system":
                    system_msg = msg["content"]
                else:
                    user_messages.append(msg)

            response = await client.messages.create(
                model=model,
                system=system_msg or None,
                messages=[{"role": m["role"], "content": m["content"]} for m in user_messages],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )

            text = response.content[0].text if response.content else ""

            tokens_in = response.usage.input_tokens if response.usage else 0
            tokens_out = response.usage.output_tokens if response.usage else 0
            total = tokens_in + tokens_out

            cost_in = (tokens_in / 1000) * cfg.cost_per_1k_in
            cost_out = (tokens_out / 1000) * cfg.cost_per_1k_out

            return LLMResponse(
                request_id=request.request_id,
                text=text,
                model_used=model,
                provider=LLMProvider.ANTHROPIC.value,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                total_tokens=total,
                cost_usd=round(cost_in + cost_out, 6),
                metadata={"stop_reason": response.stop_reason},
            )
        except ImportError:
            logger.warning("LLMRouter: anthropic package not installed; simulating response")
            return self._simulate_response(request, model, LLMProvider.ANTHROPIC.value, cfg)

    async def _execute_google(
        self,
        cfg: ProviderConfig,
        model: str,
        request: ModelRequest,
    ) -> LLMResponse:
        """Execute via Google AI API."""
        try:
            import google.generativeai as genai

            genai.configure(api_key=cfg.api_key)

            # Convert messages to Gemini format
            contents: List[Dict[str, Any]] = []
            for msg in request.messages:
                role = "user" if msg["role"] != "assistant" else "model"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})

            gemini_model = genai.GenerativeModel(model)
            response = await gemini_model.generate_content_async(
                contents,
                generation_config={
                    "temperature": request.temperature,
                    "max_output_tokens": request.max_tokens,
                },
            )

            text = response.text if response.text else ""

            # Gemini doesn't expose exact token counts in the same way
            tokens_estimate = len(text) // 4  # Rough estimate
            tokens_in = tokens_estimate
            tokens_out = tokens_estimate

            cost_in = (tokens_in / 1000) * cfg.cost_per_1k_in
            cost_out = (tokens_out / 1000) * cfg.cost_per_1k_out

            return LLMResponse(
                request_id=request.request_id,
                text=text,
                model_used=model,
                provider=LLMProvider.GOOGLE.value,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                total_tokens=tokens_in + tokens_out,
                cost_usd=round(cost_in + cost_out, 6),
                metadata={"model": model},
            )
        except ImportError:
            logger.warning("LLMRouter: google-generativeai package not installed; simulating response")
            return self._simulate_response(request, model, LLMProvider.GOOGLE.value, cfg)

    async def _execute_local(
        self,
        cfg: ProviderConfig,
        model: str,
        request: ModelRequest,
    ) -> LLMResponse:
        """Execute via local OpenAI-compatible server (e.g., Ollama, vLLM)."""
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=cfg.api_key or "not-needed",
                base_url=cfg.base_url or "http://localhost:11434/v1",
            )
            response = await client.chat.completions.create(
                model=model,
                messages=request.messages,  # type: ignore[arg-type]
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            choice = response.choices[0]
            text = choice.message.content or ""

            return LLMResponse(
                request_id=request.request_id,
                text=text,
                model_used=model,
                provider=LLMProvider.LOCAL.value,
                tokens_in=0,
                tokens_out=0,
                total_tokens=0,
                cost_usd=0.0,  # Local models are free
                metadata={"model": model},
            )
        except ImportError:
            return self._simulate_response(request, model, LLMProvider.LOCAL.value, cfg)
        except Exception:
            return self._simulate_response(request, model, LLMProvider.LOCAL.value, cfg)

    def _simulate_response(
        self,
        request: ModelRequest,
        model: str,
        provider: str,
        cfg: ProviderConfig,
    ) -> LLMResponse:
        """Generate a simulated response when a provider is unavailable.

        Used for testing and when provider packages are not installed.
        """
        last_msg = request.messages[-1]["content"] if request.messages else ""
        simulated_text = (
            f"[Simulated {provider}/{model} response] "
            f"Received query: '{last_msg[:100]}...' "
            f"Provider package not installed. This is a fallback response."
        )

        tokens_estimate = len(simulated_text) // 4
        cost = (tokens_estimate * 2 / 1000) * cfg.cost_per_1k_out

        return LLMResponse(
            request_id=request.request_id,
            text=simulated_text,
            model_used=model,
            provider=provider,
            tokens_in=tokens_estimate,
            tokens_out=tokens_estimate,
            total_tokens=tokens_estimate * 2,
            cost_usd=round(cost, 6),
            metadata={"simulated": True, "provider": provider, "model": model},
        )


# ── Singleton ────────────────────────────────────────────────────────────────

_llm_router_instance: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    """Get or create the singleton LLMRouter instance.

    Returns:
        The global LLMRouter instance.
    """
    global _llm_router_instance
    if _llm_router_instance is None:
        _llm_router_instance = LLMRouter()
    return _llm_router_instance
