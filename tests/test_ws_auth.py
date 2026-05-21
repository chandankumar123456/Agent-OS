import pytest
from fastapi import WebSocket
from unittest.mock import AsyncMock, MagicMock, patch

from core.api.ws import websocket_endpoint


@pytest.mark.asyncio
async def test_websocket_missing_token():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.path_params = {"task_id": "abc-123"}
    
    with patch("core.api.ws.verify_access_token", return_value=None) as mock_verify:
        await websocket_endpoint(mock_ws, "")
    
    mock_ws.close.assert_called_once_with(code=1008, reason="Missing token")
    mock_verify.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_valid_token():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.path_params = {"task_id": "abc-123"}
    
    with patch("core.api.ws.verify_access_token", return_value={"sub": "user-1"}) as mock_verify:
        with patch("core.api.ws.manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()
            mock_ws.receive_text = AsyncMock(side_effect=["ping", Exception("done")])
            
            try:
                await websocket_endpoint(mock_ws, "valid.jwt.token")
            except Exception:
                pass
    
    mock_verify.assert_called_once_with("valid.jwt.token")


@pytest.mark.asyncio
async def test_websocket_url_encoded_token():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.path_params = {"task_id": "abc-123"}
    # Token with URL-encoded dots
    url_encoded = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9%2EeyJzdWIiOiIxIn0%2ErTCH8cLoGxAm_xw68z-zXVKi9ie6xJn9tnVWjd_9ftE"
    
    with patch("core.api.ws.verify_access_token", return_value={"sub": "user-1"}) as mock_verify:
        with patch("core.api.ws.manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()
            mock_ws.receive_text = AsyncMock(side_effect=Exception("stop"))
            await websocket_endpoint(mock_ws, url_encoded)

    mock_verify.assert_called_once()
    call_args = mock_verify.call_args[0][0]
    assert "." in call_args


@pytest.mark.asyncio
async def test_websocket_bearer_prefix_token():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.path_params = {"task_id": "abc-123"}
    
    with patch("core.api.ws.verify_access_token", return_value={"sub": "user-1"}) as mock_verify:
        with patch("core.api.ws.manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()
            mock_ws.receive_text = AsyncMock(side_effect=Exception("stop"))
            await websocket_endpoint(mock_ws, "Bearer valid.jwt.token")

    mock_verify.assert_called_once_with("valid.jwt.token")


@pytest.mark.asyncio
async def test_websocket_malformed_token():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.path_params = {"task_id": "abc-123"}
    
    with patch("core.api.ws.verify_access_token") as mock_verify:
        await websocket_endpoint(mock_ws, "not.a.valid.jwt.too.many.segments")
    
    mock_ws.close.assert_called_once_with(code=1008, reason="Malformed token")
    mock_verify.assert_not_called()
