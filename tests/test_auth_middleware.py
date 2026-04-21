import asyncio

from app.middleware.auth import APIKeyMiddleware


async def _dispatch(path: str, headers: list[tuple[bytes, bytes]] | None = None):
    called = False

    async def call_next(request):
        nonlocal called
        called = True

        class Response:
            status_code = 200

        return Response()

    middleware = APIKeyMiddleware(lambda *args, **kwargs: None, api_keys=[])
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
        "client": ("testclient", 12345),
        "server": ("testserver", 80),
        "root_path": "",
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    from starlette.requests import Request

    request = Request(scope, receive)
    response = await middleware.dispatch(request, call_next)
    return called, response


def test_signup_route_is_not_blocked_without_credentials():
    called, response = asyncio.run(_dispatch("/api/v1/auth/signup"))

    assert called is True
    assert response is not None
