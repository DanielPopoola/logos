import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.request_context import get_request_id
from app.schemas.response import APIResponse, ErrorDetail

logger = logging.getLogger(__name__)

INTERNAL_ERROR_MESSAGE = "Something went wrong on our end. Please try again."
REQUEST_ID_HEADER = "X-Request-ID"


class UnhandledExceptionMiddleware:
    """A true last-resort safety net for unhandled exceptions.

    Unlike app.add_exception_handler(Exception, ...), this is a raw ASGI
    middleware, not built on Starlette's BaseHTTPMiddleware - it wraps the
    entire downstream ASGI call in one try/except, so it doesn't depend on
    FastAPI's exception-handler dispatch returning a response cleanly to
    outer middleware (a real, documented Starlette limitation - outer
    BaseHTTPMiddleware header mutations aren't reliably applied on that
    path). Nothing below this middleware can escape it.

    Must be added after RequestIDMiddleware (Starlette's add_middleware
    prepends, so the last one added is outermost) - that ordering is what
    guarantees request_id is already set by the time an exception reaches
    here.

    AppException is unaffected: it's still handled by FastAPI's
    add_exception_handler machinery, which runs deeper in the stack and
    never raises past this layer. This middleware only ever sees exceptions
    nothing else was registered to handle.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            request_id = get_request_id()
            logger.error(
                "Unhandled exception at middleware layer: %s %s",
                scope.get("method", "?"),
                scope.get("path", "?"),
                exc_info=exc,
            )
            body = APIResponse.fail(
                ErrorDetail(
                    code="internal_error",
                    message=INTERNAL_ERROR_MESSAGE,
                    request_id=request_id,
                )
            )
            response = JSONResponse(
                status_code=500,
                content=body.model_dump(),
                headers={REQUEST_ID_HEADER: request_id},
            )
            await response(scope, receive, send)
