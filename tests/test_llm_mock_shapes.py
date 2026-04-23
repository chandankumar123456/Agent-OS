import pytest

from app.agents.llm_client import LLMClient


def test_llm_client_requires_api_key(monkeypatch):
    monkeypatch.setattr("app.agents.llm_client.settings.OPENAI_API_KEY", None, raising=False)

    with pytest.raises(RuntimeError, match="OpenAI API key is required"):
        LLMClient(api_key=None)
