import pytest
from fastapi import WebSocket
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.ws import websocket_endpoint


@pytest.mark.asyncio
async def test_websocket_missing_token():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.path_params = {"task_id": "abc-123"}
    
    with patch("app.api.ws.verify_access_token", return_value=None) as mock_verify:
        await websocket_endpoint(mock_ws, "")
    
    mock_ws.close.assert_called_once_with(code=1008, reason="Missing token")
    mock_verify.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_valid_token():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.path_params = {"task_id": "abc-123"}
    
    with patch("app.api.ws.verify_access_token", return_value={"sub": "user-1"}) as mock_verify:
        with patch("app.api.ws.manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_ws.receive_text = AsyncMock(side_effect=["ping", Exception("done")])
            
            try:
                await websocket_endpoint(mock_ws, "valid.jwt.token")
            except Exception:
                pass
    
    mock_verify.assert_called_once_with("valid.jwt.token")
