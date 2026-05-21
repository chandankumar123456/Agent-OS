"""Tests for DeterministicVerificationEngine."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.capabilities.models import VerificationResult
from core.capabilities.verification import DeterministicVerificationEngine


def _make_mock_httpx_client(response_or_side_effect):
    """Return a mock httpx.AsyncClient that works as an async context manager."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    if isinstance(response_or_side_effect, BaseException):
        client.get = AsyncMock(side_effect=response_or_side_effect)
    elif callable(response_or_side_effect) and not isinstance(response_or_side_effect, MagicMock):
        client.get = AsyncMock(side_effect=response_or_side_effect)
    else:
        client.get = AsyncMock(return_value=response_or_side_effect)
    return client


@pytest.fixture
def engine():
    return DeterministicVerificationEngine()


@pytest.mark.asyncio
async def test_verify_unknown_type_returns_skipped(engine):
    report = await engine.verify("task-1", "step-1", "unknown_type", {})
    assert report.result == VerificationResult.SKIPPED
    assert report.verifier_type == "llm"
    assert "No deterministic verifier" in (report.failure_reason or "")


class TestFileExists:
    @pytest.mark.asyncio
    async def test_pass_when_file_exists(self, engine, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello")
        result, evidence = await engine._verify_file_exists({"path": str(file_path)})
        assert result == VerificationResult.PASS
        assert evidence["path"] == str(file_path)
        assert "size" in evidence

    @pytest.mark.asyncio
    async def test_fail_when_file_missing(self, engine, tmp_path):
        missing = tmp_path / "missing.txt"
        result, evidence = await engine._verify_file_exists({"path": str(missing)})
        assert result == VerificationResult.FAIL
        assert "not found" in evidence["error"]
        assert evidence.get("retryable") is True

    @pytest.mark.asyncio
    async def test_fail_when_no_path(self, engine):
        result, evidence = await engine._verify_file_exists({})
        assert result == VerificationResult.FAIL
        assert "No path provided" in evidence["error"]


class TestFileContains:
    @pytest.mark.asyncio
    async def test_pass_when_content_present(self, engine, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello world")
        result, evidence = await engine._verify_file_contains(
            {"path": str(file_path), "content": "world"}
        )
        assert result == VerificationResult.PASS
        assert evidence["found"] is True

    @pytest.mark.asyncio
    async def test_fail_when_content_missing(self, engine, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello world")
        result, evidence = await engine._verify_file_contains(
            {"path": str(file_path), "content": "missing"}
        )
        assert result == VerificationResult.FAIL
        assert "not found" in evidence["error"]

    @pytest.mark.asyncio
    async def test_fail_when_file_missing(self, engine, tmp_path):
        missing = tmp_path / "missing.txt"
        result, evidence = await engine._verify_file_contains(
            {"path": str(missing), "content": "x"}
        )
        assert result == VerificationResult.FAIL
        assert evidence.get("retryable") is True

    @pytest.mark.asyncio
    async def test_fail_when_missing_params(self, engine):
        result, evidence = await engine._verify_file_contains({"path": "/tmp/x"})
        assert result == VerificationResult.FAIL
        assert "required" in evidence["error"].lower()


class TestCodeRuns:
    @pytest.mark.asyncio
    async def test_pass_with_expected_output(self, engine):
        result, evidence = await engine._verify_code_runs(
            {"command": 'python -c "print(\\"hello\\")"', "expected_output": "hello"}
        )
        assert result == VerificationResult.PASS
        assert "hello" in evidence["output"]

    @pytest.mark.asyncio
    async def test_pass_without_expected_output(self, engine):
        result, evidence = await engine._verify_code_runs(
            {"command": 'python -c "print(\\"hello\\")"'}
        )
        assert result == VerificationResult.PASS
        assert "hello" in evidence["output"]

    @pytest.mark.asyncio
    async def test_fail_on_nonzero_exit(self, engine):
        result, evidence = await engine._verify_code_runs(
            {"command": 'python -c "import sys; sys.exit(1)"'}
        )
        assert result == VerificationResult.FAIL
        assert "Exit code 1" in evidence["error"]

    @pytest.mark.asyncio
    async def test_fail_on_output_mismatch(self, engine):
        result, evidence = await engine._verify_code_runs(
            {"command": 'python -c "print(\\"world\\")"', "expected_output": "hello"}
        )
        assert result == VerificationResult.FAIL
        assert "Expected output not found" in evidence["error"]

    @pytest.mark.asyncio
    async def test_fail_on_timeout(self, engine):
        mock_proc = MagicMock()
        mock_proc.communicate = MagicMock(return_value=asyncio.Future())
        mock_proc.kill = MagicMock()

        with patch(
            "core.capabilities.verification.asyncio.create_subprocess_shell",
            new=AsyncMock(return_value=mock_proc),
        ):
            with patch(
                "core.capabilities.verification.asyncio.wait_for",
                side_effect=asyncio.TimeoutError,
            ):
                result, evidence = await engine._verify_code_runs(
                    {"command": "sleep 100"}
                )
        assert result == VerificationResult.FAIL
        assert "timed out" in evidence["error"].lower()
        assert evidence.get("retryable") is True
        mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_fail_when_no_command(self, engine):
        result, evidence = await engine._verify_code_runs({})
        assert result == VerificationResult.FAIL
        assert "No command provided" in evidence["error"]


class TestDeploymentHealthy:
    @pytest.mark.asyncio
    async def test_pass_on_200(self, engine):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.elapsed.total_seconds.return_value = 0.1

        mock_client = _make_mock_httpx_client(mock_response)

        with patch("core.capabilities.verification.httpx.AsyncClient", return_value=mock_client):
            result, evidence = await engine._verify_deployment_healthy(
                {"url": "http://example.com"}
            )
        assert result == VerificationResult.PASS
        assert evidence["status_code"] == 200

    @pytest.mark.asyncio
    async def test_pass_on_404(self, engine):
        # 404 is < 500, so PASS per implementation
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.elapsed.total_seconds.return_value = 0.1

        mock_client = _make_mock_httpx_client(mock_response)

        with patch("core.capabilities.verification.httpx.AsyncClient", return_value=mock_client):
            result, evidence = await engine._verify_deployment_healthy(
                {"url": "http://example.com"}
            )
        assert result == VerificationResult.PASS

    @pytest.mark.asyncio
    async def test_fail_on_500(self, engine):
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = _make_mock_httpx_client(mock_response)

        with patch("core.capabilities.verification.httpx.AsyncClient", return_value=mock_client):
            result, evidence = await engine._verify_deployment_healthy(
                {"url": "http://example.com"}
            )
        assert result == VerificationResult.FAIL
        assert "HTTP 500" in evidence["error"]
        assert evidence.get("retryable") is True

    @pytest.mark.asyncio
    async def test_fail_on_connection_error(self, engine):
        mock_client = _make_mock_httpx_client(Exception("Connection refused"))

        with patch("core.capabilities.verification.httpx.AsyncClient", return_value=mock_client):
            result, evidence = await engine._verify_deployment_healthy(
                {"url": "http://example.com"}
            )
        assert result == VerificationResult.FAIL
        assert "retryable" in evidence

    @pytest.mark.asyncio
    async def test_fail_when_no_url(self, engine):
        result, evidence = await engine._verify_deployment_healthy({})
        assert result == VerificationResult.FAIL
        assert "No URL provided" in evidence["error"]


class TestWebContent:
    @pytest.mark.asyncio
    async def test_pass_without_pattern(self, engine):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>Hello</html>"

        mock_client = _make_mock_httpx_client(mock_response)

        with patch("core.capabilities.verification.httpx.AsyncClient", return_value=mock_client):
            result, evidence = await engine._verify_web_content(
                {"url": "http://example.com"}
            )
        assert result == VerificationResult.PASS
        assert evidence["length"] == len("<html>Hello</html>")

    @pytest.mark.asyncio
    async def test_pass_with_matching_pattern(self, engine):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>Hello</html>"

        mock_client = _make_mock_httpx_client(mock_response)

        with patch("core.capabilities.verification.httpx.AsyncClient", return_value=mock_client):
            result, evidence = await engine._verify_web_content(
                {"url": "http://example.com", "pattern": r"Hello"}
            )
        assert result == VerificationResult.PASS

    @pytest.mark.asyncio
    async def test_fail_when_pattern_not_found(self, engine):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>Hello</html>"

        mock_client = _make_mock_httpx_client(mock_response)

        with patch("core.capabilities.verification.httpx.AsyncClient", return_value=mock_client):
            result, evidence = await engine._verify_web_content(
                {"url": "http://example.com", "pattern": r"Goodbye"}
            )
        assert result == VerificationResult.FAIL
        assert "Pattern" in evidence["error"]

    @pytest.mark.asyncio
    async def test_fail_on_request_error(self, engine):
        mock_client = _make_mock_httpx_client(Exception("timeout"))

        with patch("core.capabilities.verification.httpx.AsyncClient", return_value=mock_client):
            result, evidence = await engine._verify_web_content(
                {"url": "http://example.com"}
            )
        assert result == VerificationResult.FAIL
        assert "retryable" in evidence

    @pytest.mark.asyncio
    async def test_fail_when_no_url(self, engine):
        result, evidence = await engine._verify_web_content({})
        assert result == VerificationResult.FAIL
        assert "No URL provided" in evidence["error"]


class TestCommandSucceeds:
    @pytest.mark.asyncio
    async def test_delegates_to_code_runs(self, engine):
        with patch.object(
            engine,
            "_verify_code_runs",
            new=AsyncMock(return_value=(VerificationResult.PASS, {"output": "ok"})),
        ) as mock_code_runs:
            result, evidence = await engine._verify_command_succeeds({"command": "ls"})
        mock_code_runs.assert_awaited_once_with({"command": "ls"})
        assert result == VerificationResult.PASS

    @pytest.mark.asyncio
    async def test_fail_when_no_command(self, engine):
        result, evidence = await engine._verify_command_succeeds({})
        assert result == VerificationResult.FAIL
        assert "No command provided" in evidence["error"]


class TestVerifyPlan:
    @pytest.mark.asyncio
    async def test_auto_detect_file_steps(self, engine, tmp_path):
        file_path = tmp_path / "output.txt"
        file_path.write_text("data")
        plan = [{"id": "s1", "step": f"write data to {file_path}"}]
        reports = await engine.verify_plan("task-1", plan)
        file_reports = [
            r for r in reports if r.checks and r.checks[0]["type"] == "file_exists"
        ]
        assert len(file_reports) >= 1
        assert any(r.result == VerificationResult.PASS for r in file_reports)

    @pytest.mark.asyncio
    async def test_auto_detect_deploy_steps(self, engine):
        mock_deploy = AsyncMock(return_value=(VerificationResult.PASS, {"status_code": 200}))
        engine._verifiers["deployment_healthy"] = mock_deploy
        plan = [{"id": "s2", "step": "deploy app to http://example.com"}]
        reports = await engine.verify_plan("task-1", plan)
        mock_deploy.assert_awaited_once()
        assert any(r.result == VerificationResult.PASS for r in reports)

    @pytest.mark.asyncio
    async def test_auto_detect_scrape_steps(self, engine):
        mock_web = AsyncMock(return_value=(VerificationResult.PASS, {"length": 100}))
        engine._verifiers["web_content"] = mock_web
        plan = [{"id": "s3", "step": "scrape http://example.com"}]
        reports = await engine.verify_plan("task-1", plan)
        mock_web.assert_awaited_once()
        assert any(r.result == VerificationResult.PASS for r in reports)

    @pytest.mark.asyncio
    async def test_auto_detect_mixed_steps(self, engine, tmp_path):
        file_path = tmp_path / "file.txt"
        file_path.write_text("x")
        with patch.object(
            engine,
            "_verify_deployment_healthy",
            new=AsyncMock(return_value=(VerificationResult.PASS, {})),
        ) as mock_deploy, patch.object(
            engine,
            "_verify_web_content",
            new=AsyncMock(return_value=(VerificationResult.PASS, {})),
        ) as mock_web:
            plan = [
                {"id": "s1", "step": f"create file {file_path}"},
                {"id": "s2", "step": "deploy to http://example.com"},
                {"id": "s3", "step": "fetch http://example.com/data"},
            ]
            reports = await engine.verify_plan("task-1", plan)
        assert len(reports) == 3
        types = [r.checks[0]["type"] for r in reports]
        assert "file_exists" in types
        assert "deployment_healthy" in types
        assert "web_content" in types

    @pytest.mark.asyncio
    async def test_no_matches_returns_empty_reports(self, engine):
        plan = [{"id": "s1", "step": "think about the problem"}]
        reports = await engine.verify_plan("task-1", plan)
        assert reports == []
