from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

from ...llm.providers import list_providers, get_provider
from ...llm.providers.schemas import ProviderConfig
from ...config.settings import settings
import httpx

router = APIRouter(prefix="/providers", tags=["providers"])


def _enabled_providers() -> List[str]:
    return [p.strip().lower() for p in settings.ENABLED_PROVIDERS.split(",") if p.strip()]


def _get_provider_config(name: str) -> ProviderConfig:
    name = name.lower()
    enabled = name in _enabled_providers()
    if name == "openai":
        return ProviderConfig(
            name="openai",
            api_key=settings.OPENAI_API_KEY,
            default_model=settings.OPENAI_MODEL,
            enabled=enabled,
        )
    elif name == "anthropic":
        return ProviderConfig(
            name="anthropic",
            api_key=settings.ANTHROPIC_API_KEY,
            enabled=enabled,
        )
    elif name == "google":
        return ProviderConfig(
            name="google",
            api_key=settings.GOOGLE_API_KEY,
            enabled=enabled,
        )
    elif name == "ollama":
        return ProviderConfig(
            name="ollama",
            base_url=settings.OLLAMA_BASE_URL,
            enabled=enabled,
        )
    else:
        raise HTTPException(status_code=404, detail="Provider not found")


@router.get("", response_model=List[ProviderConfig])
async def list_configured_providers():
    providers = []
    for name in list_providers():
        providers.append(_get_provider_config(name))
    return providers


@router.post("/test", response_model=Dict[str, Any])
async def test_provider(config: ProviderConfig):
    try:
        provider = get_provider(config.name)
        from ...llm.providers.schemas import ChatMessage

        resp = await provider.chat(
            messages=[
                ChatMessage(
                    role="user",
                    content="Hello, this is a test. Reply with 'OK'.",
                )
            ],
            model=config.default_model,
            temperature=0.0,
            max_tokens=10,
        )
        return {
            "success": True,
            "provider": config.name,
            "response": resp.content,
        }
    except Exception as e:
        return {"success": False, "provider": config.name, "error": str(e)}


@router.get("/models", response_model=Dict[str, List[str]])
async def list_available_models():
    result: Dict[str, List[str]] = {}
    enabled = _enabled_providers()
    if "openai" in enabled:
        result["openai"] = [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
        ]
    if "anthropic" in enabled:
        result["anthropic"] = [
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
        ]
    if "google" in enabled:
        result["google"] = [
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-pro",
        ]
    if "ollama" in enabled:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=10.0
                )
                r.raise_for_status()
                data = r.json()
                models = [m["name"] for m in data.get("models", [])]
                result["ollama"] = models if models else ["llama3", "mistral", "codellama"]
        except Exception:
            result["ollama"] = ["llama3", "mistral", "codellama"]
    return result
