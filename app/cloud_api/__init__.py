"""AgentOS Cloud/HTTP API Module.

This package contains the FastAPI application and all HTTP/WebSocket-related
components for cloud deployment of AgentOS. In desktop-native mode (gRPC),
this package is NOT imported - the Go Supervisor provides the HTTP API instead.

Usage (cloud mode):
    from app.cloud_api.main import app
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""
