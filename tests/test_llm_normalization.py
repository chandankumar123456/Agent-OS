from app.agents.planner import PlannerAgent


def test_planner_normalizes_wrapped_steps_response():
    agent = PlannerAgent()

    result = agent._normalize_plan_response({"steps": [{"step": "collect data", "agent_type": "executor"}]})

    assert result == [{"id": "step_1", "step": "collect data", "agent_type": "executor", "depends_on": []}]
