import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_websocket_valid_token():
    from app.auth.utils import create_access_token
    token = create_access_token({"sub": "test-user", "email": "test@test.com", "role": "user"})

    with client.websocket_connect(f"/ws/tasks/test-task-123?token={token}") as ws:
        ws.send_text("ping")
        data = ws.receive_text()
        assert data == "pong"


def test_websocket_missing_token():
    # FastAPI closes with 1008 before accept when token is missing
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/tasks/test-task-123") as ws:
            pass


def test_websocket_malformed_token():
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/tasks/test-task-123?token=not-a-jwt") as ws:
            pass
