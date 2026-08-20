import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = structlog.get_logger()


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start_time = time.monotonic()

        structlog.contextvars.bind_contextvars(request_id=request_id)

        logger.info("request_started", method=request.method, path=request.url.path)

        try:
            response = await call_next(request)

            duration_ms = round((time.monotonic() - start_time) * 1000)

            logger.info("request_completed", status=response.status_code, duration_ms=duration_ms)

            response.headers["X-Request-ID"] = request_id

            return response
        finally:
            structlog.contextvars.clear_contextvars()
