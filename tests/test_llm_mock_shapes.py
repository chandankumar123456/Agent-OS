import asyncio

from app.agents.llm_client import LLMClient


def test_mock_planner_json_returns_steps_shape():
    client = LLMClient(api_key=None)

    async def run():
        return await client.complete_json([
            {"role": "system", "content": "You are a Planner agent for Agent-OS."}
        ])

    result = asyncio.run(run())

    assert isinstance(result, dict)
    assert "steps" in result
    assert isinstance(result["steps"], list)
    assert result["steps"] and isinstance(result["steps"][0], dict)
    assert "step" in result["steps"][0]
