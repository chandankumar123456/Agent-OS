from .registry import LLMProvider, OpenAIProvider, AnthropicProvider, GoogleProvider, OllamaProvider
from .schemas import ChatMessage, ChatResponse, ProviderConfig

_PROVIDERS: dict[str, LLMProvider] = {}


def get_provider(name: str) -> LLMProvider:
    name = name.lower()
    if name in _PROVIDERS:
        return _PROVIDERS[name]
    if name == "openai":
        p = OpenAIProvider()
    elif name == "anthropic":
        p = AnthropicProvider()
    elif name == "google":
        p = GoogleProvider()
    elif name == "ollama":
        p = OllamaProvider()
    else:
        raise ValueError(f"Unknown provider: {name}")
    _PROVIDERS[name] = p
    return p


def list_providers() -> list[str]:
    return ["openai", "anthropic", "google", "ollama"]
