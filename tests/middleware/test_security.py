from fastapi import Request
from starlette.responses import Response

from app.middleware.security import RateLimitMiddleware


def _request(path: str, client_host: str = "198.51.100.10") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": [],
            "client": (client_host, 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


async def _next(_request: Request) -> Response:
    return Response(status_code=200)


def test_rate_limit_buckets_classify_sensitive_routes():
    middleware = RateLimitMiddleware(_next)

    assert middleware._bucket(_request("/v1/auth/google/login"))[0] == "auth"
    assert middleware._bucket(_request("/v1/ask"))[0] == "llm"
    assert middleware._bucket(_request("/v1/sermons"))[0] == "default"


async def test_rate_limit_rejects_requests_after_auth_threshold():
    middleware = RateLimitMiddleware(_next)
    request = _request("/v1/auth/google/login")

    responses = [await middleware.dispatch(request, _next) for _ in range(21)]

    assert all(response.status_code == 200 for response in responses[:20])
    assert responses[-1].status_code == 429
    assert responses[-1].headers["Retry-After"] == "60"


async def test_rate_limit_isolated_by_client_identity():
    middleware = RateLimitMiddleware(_next)

    first_client = _request("/v1/auth/google/login", "198.51.100.10")
    second_client = _request("/v1/auth/google/login", "198.51.100.11")

    for _ in range(20):
        await middleware.dispatch(first_client, _next)

    first_response = await middleware.dispatch(first_client, _next)
    second_response = await middleware.dispatch(second_client, _next)

    assert first_response.status_code == 429
    assert second_response.status_code == 200
