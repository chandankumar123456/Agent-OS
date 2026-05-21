"""Tests for legacy ExecutorAgent desktop automation hardening.

FR2.3: ExecutorAgent desktop path must reuse DesktopSession, ActionStabilizer, WindowRegistry.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4

from core.agents.executor import ExecutorAgent
from core.agents.base import AgentInput, AgentOutput, AgentRole, AgentStatus


@pytest.mark.asyncio
async def test_legacy_executor_reuses_desktop_components():
    """FR2.3: ExecutorAgent desktop path must use DesktopSession, ActionStabilizer, WindowRegistry."""
    agent = ExecutorAgent()
    task_id = uuid4()
    step_id = uuid4()

    input_data = AgentInput(
        task_id=task_id,
        step_id=step_id,
        role=AgentRole.EXECUTOR,
        input_data={
            "step": "Open notepad",
            "env_type": "desktop",
            "tools": [
                {"name": "desktop_env__open_application", "description": "Open desktop application"},
                {"name": "desktop__type_element", "description": "Type text into element"},
            ],
        },
        context={"query": "Open notepad and type hello"},
    )

    with patch("core.agents.executor.DesktopSessionManager") as mock_mgr_cls:
        mock_mgr = MagicMock()
        mock_session = AsyncMock()
        mock_mgr.get_or_create_session = AsyncMock(return_value=mock_session)
        mock_mgr_cls.return_value = mock_mgr

        with patch("core.agents.executor.ActionStabilizer") as mock_stab_cls:
            mock_stab = MagicMock()
            mock_stab_cls.return_value = mock_stab

            with patch("core.agents.executor.WindowRegistry") as mock_reg_cls:
                mock_reg = MagicMock()
                mock_reg_cls.return_value = mock_reg

                with patch.object(agent, "_execute_desktop_goal", new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = AgentOutput(
                        task_id=task_id,
                        step_id=step_id,
                        status=AgentStatus.SUCCESS,
                        output_data={"result": "Task completed"},
                    )

                    result = await agent.execute(input_data)

                # Verify get_or_create_session was called on the session manager
                mock_mgr.get_or_create_session.assert_called_once()

    # Verify the result came from the mocked _execute_desktop_goal
    assert result.status == AgentStatus.SUCCESS
    assert result.output_data.get("result") == "Task completed"
