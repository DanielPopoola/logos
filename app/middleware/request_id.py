import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.request_context import reset_request_id, set_request_id

REQUEST_ID_HEADER = "X-Request-ID"
logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns a request_id to every request - reusing one supplied by the
    client via X-Request-ID (so a request can be traced across services),
    or generating a fresh one otherwise. The ID is bound into a context var
    for the duration of the request, so any log line emitted while handling
    it can pick it up without threading it through every function call, and
    is echoed back on the response so the client can correlate it too.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request_id_token = set_request_id(request_id)
        started_at = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        except Exception:
            logger.exception(
                "HTTP request failed",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status": 500,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                },
            )
            raise
        finally:
            if response is not None:
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                level = logging.WARNING if response.status_code >= 400 else logging.INFO
                logger.log(
                    level,
                    "HTTP request completed",
                    extra={
                        "http_method": request.method,
                        "http_path": request.url.path,
                        "http_status": response.status_code,
                        "duration_ms": duration_ms,
                    },
                )
            reset_request_id(request_id_token)
