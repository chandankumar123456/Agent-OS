from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import json
from ..guardrails.validator import InputValidator
from ..orchestrator.errors import UnrecoverableError

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
                            return json_response(e.http_status, {
                                "error": {
                                    "code": e.code.value if hasattr(e.code, "value") else str(e.code),
                                    "message": e.message,
                                    "context": e.context
                                }
                            })
                
                # Reset request body so the route can read it again
                async def receive():
                    return {"type": "http.request", "body": body}
                request._receive = receive
                
            except Exception as e:
                # If JSON parsing fails, let the standard FastAPI validator handle it
                pass
                
        return await call_next(request)

def json_response(status_code: int, content: dict):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content=content)
