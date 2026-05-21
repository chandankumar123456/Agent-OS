from core.agents.planner import PlannerAgent


def test_planner_normalizes_wrapped_steps_response():
    agent = PlannerAgent()

    result = agent._normalize_plan_response({"steps": [{"step": "collect data", "agent_type": "executor"}]})

    assert result[0]["id"] == "step_1"
    assert result[0]["step"] == "collect data"
    assert result[0]["agent_type"] == "executor"
    assert result[0]["depends_on"] == []
    assert result[0]["step_type"] == "general"
    assert isinstance(result[0]["allowed_tools"], list)
    assert isinstance(result[0]["fallback_tools"], list)
    assert result[0]["expected_output"] == ""
    assert result[0]["required"] is False
