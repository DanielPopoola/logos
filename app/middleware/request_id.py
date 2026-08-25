import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.request_context import set_request_id

REQUEST_ID_HEADER = "X-Request-ID"


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
        set_request_id(request_id)

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
