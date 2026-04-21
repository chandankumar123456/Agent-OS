from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict, Any
import time
from ..logs.logger import logger


class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.request_count = 0
        self.error_count = 0
        self.total_response_time = 0.0
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        response = await call_next(request)
        
        process_time = time.time() - start_time
        self.request_count += 1
        self.total_response_time += process_time
        
        if response.status_code >= 400:
            self.error_count += 1
        
        return response
    
    def get_metrics(self) -> Dict[str, Any]:
        avg_response_time = (
            self.total_response_time / self.request_count
            if self.request_count > 0 else 0
        )
        
        error_rate = (
            self.error_count / self.request_count
            if self.request_count > 0 else 0
        )
        
        return {
            "requests_total": self.request_count,
            "errors_total": self.error_count,
            "error_rate": error_rate,
            "avg_response_time": avg_response_time,
            "requests_per_minute": self.request_count
        }
    
    def reset(self):
        self.request_count = 0
        self.error_count = 0
        self.total_response_time = 0.0


metrics_middleware = MetricsMiddleware