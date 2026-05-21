
import httpx
from openai import AsyncOpenAI
from typing import Optional, List, Dict, Any
from ..config.settings import settings
from ..logs.logger import logger
from ..logs.metrics import metrics_collector


def _create_openai_client(api_key: str) -> AsyncOpenAI:
    """Create an AsyncOpenAI client with SSL error handling.

    If the SSL_CERT_FILE environment variable points to a missing file,
    the default httpx transport will raise FileNotFoundError. This helper
    catches that and retries with SSL verification disabled.
    """
    try:
        client = AsyncOpenAI(api_key=api_key)
        return client
    except (FileNotFoundError, OSError) as e:
        logger.error(
            f"SSL certificate file not found. Falling back to INSECURE connection (verify=False). "
            f"Fix by setting SSL_CERT_FILE to a valid CA bundle path. Error: {e}"
        )
        http_client = httpx.AsyncClient(verify=False)
        client = AsyncOpenAI(api_key=api_key, http_client=http_client)
        return client


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD based on model pricing."""
    model_lower = model.lower()
    if "gpt-4o-mini" in model_lower:
        return (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000
    elif "gpt-4o" in model_lower:
        return (input_tokens * 5.0 + output_tokens * 15.0) / 1_000_000
    elif "o1" in model_lower or "o3" in model_lower:
        return (input_tokens * 15.0 + output_tokens * 60.0) / 1_000_000
    else:
        return (input_tokens + output_tokens) * 0.00001


def _extract_json(text: str) -> str:
    """Extract a JSON object or array from text, stripping markdown fences."""
    # Strip markdown code fences
    stripped = text.strip()
    if stripped.startswith("```"):
        # Remove opening fence
        stripped = stripped[3:]
        if stripped.startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()
        # Remove closing fence
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    # Find first { or [
    start = -1
    for i, ch in enumerate(stripped):
        if ch in "{[":
            start = i
            break
    if start == -1:
        return stripped
    # Count braces respecting strings and escapes
    target = stripped[start]
    end_target = "}" if target == "{" else "]"
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(stripped)):
        ch = stripped[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"' and not in_string:
            in_string = True
        elif ch == '"' and in_string:
            in_string = False
        if not in_string:
            if ch == target:
                depth += 1
            elif ch == end_target:
                depth -= 1
                if depth == 0:
                    return stripped[start:i + 1]
    return stripped[start:]


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

        self.client = _create_openai_client(self.api_key)
        logger.info(f"LLM client initialized with model: {self.model}")

    async def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        task_id: Optional[str] = None,
    ) -> str:
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens is not None:
                if self.model.startswith(("o1", "o3")) or "gpt-5" in self.model:
                    kwargs["max_completion_tokens"] = max_tokens
                else:
                    kwargs["max_tokens"] = max_tokens
            response = await self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("LLM returned empty content (possible content filter or refusal)")

            if response.usage:
                input_tokens = response.usage.prompt_tokens or 0
                output_tokens = response.usage.completion_tokens or 0
                metrics_collector.record_tokens(self.model, input_tokens, output_tokens)
                if task_id:
                    try:
                        from ..memory.long_term import token_usage_repo
                        total_tokens = response.usage.total_tokens or (input_tokens + output_tokens)
                        cost_usd = _calculate_cost(self.model, input_tokens, output_tokens)
                        await token_usage_repo.create(
                            task_id=task_id,
                            model=self.model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            total_tokens=total_tokens,
                            cost_usd=cost_usd,
                        )
                    except Exception as db_err:
                        logger.warning(f"Failed to persist token usage: {db_err}")

            return content
        except Exception as e:
            logger.error(f"LLM completion failed: {e}")
            raise

    async def achain(self, prompt: str):
        """Simple achain-compatible interface returning an object with .content.

        Used by DesktopGoalLoop._decide_action and other LangChain-pattern code.
        """
        class _AchainResult:
            def __init__(self, content):
                self.content = content

        result = await self.complete([{"role": "user", "content": prompt}])
        return _AchainResult(result)

    async def complete_json(
        self,
        messages: List[Dict[str, str]],
        response_schema: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
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
                # OpenAI requires additionalProperties: false at the root of the schema
                schema = dict(response_schema)

                def _inject_additional_properties_false(node: Any) -> None:
                    """Recursively inject additionalProperties: false into all object schemas."""
                    if not isinstance(node, dict):
                        return
                    if node.get("type") == "object":
                        node["additionalProperties"] = False
                    for key in ("properties", "patternProperties", "$defs", "definitions"):
                        if key in node and isinstance(node[key], dict):
                            for child in node[key].values():
                                _inject_additional_properties_false(child)
                    for key in ("items", "prefixItems", "allOf", "anyOf", "oneOf"):
                        if key in node and isinstance(node[key], list):
                            for child in node[key]:
                                _inject_additional_properties_false(child)
                        elif key in node and isinstance(node[key], dict):
                            _inject_additional_properties_false(node[key])
                    if "properties" in node and isinstance(node.get("properties"), dict):
                        for child in node["properties"].values():
                            _inject_additional_properties_false(child)

                _inject_additional_properties_false(schema)
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response",
                        "schema": schema,
                        "strict": True,
                    },
                }
            response = await self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("LLM returned empty content (possible content filter or refusal)")
            content = _extract_json(content)

            if response.usage:
                input_tokens = response.usage.prompt_tokens or 0
                output_tokens = response.usage.completion_tokens or 0
                metrics_collector.record_tokens(self.model, input_tokens, output_tokens)
                if task_id:
                    try:
                        from ..memory.long_term import token_usage_repo
                        total_tokens = response.usage.total_tokens or (input_tokens + output_tokens)
                        cost_usd = _calculate_cost(self.model, input_tokens, output_tokens)
                        await token_usage_repo.create(
                            task_id=task_id,
                            model=self.model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            total_tokens=total_tokens,
                            cost_usd=cost_usd,
                        )
                    except Exception as db_err:
                        logger.warning(f"Failed to persist token usage: {db_err}")

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
