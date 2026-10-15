import time
import uuid

import structlog
from starlette import status
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.error_codes import ErrorCode
from app.core.exception_handlers import build_error_response, global_exception_handler

logger = structlog.get_logger()

# The largest legitimate body, 50 splits with full descriptions, is about 630 KB
MAX_REQUEST_BODY_BYTES = 1024 * 1024


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


class RequestBodyLimitMiddleware:
    """Rejects a request body above max_body_size before it is parsed.

    Pure ASGI rather than BaseHTTPMiddleware: the limit has to wrap receive,
    which BaseHTTPMiddleware does not expose.
    """

    def __init__(self, app: ASGIApp, max_body_size: int) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        detail = f"Request body must not exceed {self.max_body_size} bytes"

        # An honest Content-Length is rejected before a single byte of the body is read
        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None and content_length.isdecimal():
            if int(content_length) > self.max_body_size:
                response = build_error_response(
                    status.HTTP_413_CONTENT_TOO_LARGE, ErrorCode.CONTENT_TOO_LARGE, detail
                )
                await response(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> Message:
            # A chunked body has no Content-Length, so the bytes are counted as they arrive
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_size:
                    # FastAPI re-raises an HTTPException from the body read; any other
                    # exception there would turn into a 400
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail)
            return message

        await self.app(scope, limited_receive, send)


class UnhandledExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            # Called inside except so the handler still sees the traceback for exc_info
            return await global_exception_handler(request, exc)
