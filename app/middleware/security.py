import hashlib
import hmac
import logging
import secrets
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config import settings

logger = logging.getLogger(__name__)

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_RATE_WINDOW_SECONDS = 60
_RATE_LIMITS = {
    "auth": 20,
    "llm": 30,
    "default": 120,
}


def _secure_cookie() -> bool:
    return settings.environment not in ("test", "development")


def _csrf_digest(token: str) -> str:
    return hmac.new(settings.google_client_secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def valid_csrf_token(cookie_token: str | None, header_token: str | None) -> bool:
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(_csrf_digest(cookie_token), _csrf_digest(header_token))


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
        is_unsafe = request.method in _UNSAFE_METHODS
        has_session_cookie = request.cookies.get("session_token") is not None
        if (
            is_unsafe
            and has_session_cookie
            and not valid_csrf_token(csrf_token, request.headers.get(CSRF_HEADER_NAME))
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF validation failed"},
            )

        if csrf_token is None:
            csrf_token = secrets.token_urlsafe(32)

        response = await call_next(request)
        if request.cookies.get(CSRF_COOKIE_NAME) is None:
            secure = _secure_cookie()
            response.set_cookie(
                CSRF_COOKIE_NAME,
                csrf_token,
                max_age=86400,
                httponly=False,
                secure=secure,
                samesite="none" if secure else "lax",
                path="/",
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    @staticmethod
    def _bucket(request: Request) -> tuple[str, int]:
        path = request.url.path
        if path.startswith("/v1/auth/"):
            return "auth", _RATE_LIMITS["auth"]
        if path.startswith("/v1/ask") or (
            path.startswith("/v1/sermons") and request.method in _UNSAFE_METHODS
        ):
            return "llm", _RATE_LIMITS["llm"]
        return "default", _RATE_LIMITS["default"]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        bucket, limit = self._bucket(request)
        client_host = request.client.host if request.client else "unknown"
        key = (client_host, bucket)
        now = time.monotonic()
        timestamps = self._requests[key]
        while timestamps and now - timestamps[0] >= _RATE_WINDOW_SECONDS:
            timestamps.popleft()
        if len(timestamps) >= limit:
            logger.warning("Request rate limit exceeded", extra={"rate_limit_bucket": bucket})
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
                headers={"Retry-After": str(_RATE_WINDOW_SECONDS)},
            )
        timestamps.append(now)
        return await call_next(request)
