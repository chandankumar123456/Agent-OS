import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..guardrails.validator import InputValidator
from ..orchestrator.errors import UnrecoverableError


def _error_payload(err: UnrecoverableError) -> dict:
    return {
        "error": {
            "code": err.code.value if hasattr(err.code, "value") else str(err.code),
            "message": err.message,
            "context": err.context,
        }
    }


class InputValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and request.url.path.endswith("/tasks"):
            try:
                # We need to consume the body to validate it
                body = await request.body()
                if body:
                    data = json.loads(body)
                    query = data.get("query")
                    config = data.get("config", {})
                    mode = data.get("mode", "task")

                    if query:
                        try:
                            InputValidator.validate_request(query, config, mode)
                        except UnrecoverableError as e:
                            return JSONResponse(
                                status_code=e.http_status,
                                content=_error_payload(e),
                            )

                # Reset request body so the route can read it again
                async def receive():
                    return {"type": "http.request", "body": body}

                request._receive = receive

            except Exception:
                # If JSON parsing fails, let the standard validator handle it
                pass

        return await call_next(request)
