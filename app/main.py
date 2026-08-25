from typing import Annotated

from fastapi import Depends, FastAPI
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.api import ask, auth, notes, search, sermons
from app.api.deps import get_current_user
from app.config import settings
from app.errors import AppException, app_exception_handler
from app.logging_config import configure_logging
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.unhandled_exceptions import UnhandledExceptionMiddleware
from app.models.user import User as UserModel
from app.sentry_config import init_sentry

configure_logging()
# FastAPI is built on Starlette - both integrations are required together,
# per Sentry's docs, or request-level context (route, method) won't be
# captured on errors.
init_sentry([StarletteIntegration(), FastApiIntegration()])

app = FastAPI(title="Logos")
app.add_middleware(RequestIDMiddleware)
# Added last so it's outermost (Starlette's add_middleware prepends) - this
# guarantees request_id is already set by RequestIDMiddleware before any
# exception reaches this last-resort catch. See UnhandledExceptionMiddleware
# for why a raw ASGI middleware is used here instead of
# add_exception_handler(Exception, ...).
app.add_middleware(UnhandledExceptionMiddleware)
app.add_exception_handler(AppException, app_exception_handler)  # ty: ignore[invalid-argument-type]
app.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
app.include_router(sermons.router, prefix="/v1/sermons", tags=["sermons"])
app.include_router(notes.router, prefix="/v1/notes", tags=["notes"])
app.include_router(search.router, prefix="/v1/search", tags=["search"])
app.include_router(ask.router, prefix="/v1/ask", tags=["ask"])


if settings.environment in ("test", "development"):

    @app.get("/v1/_protected_ping", include_in_schema=False)
    def protected_ping(user: Annotated[UserModel, Depends(get_current_user)]):
        """Test-only fixture route: a thin auth-check endpoint for
        exercising get_current_user in isolation from any real route's
        response shape. Never registered in production.
        """
        return {"user_id": str(user.id)}

    @app.get("/v1/_boom", include_in_schema=False)
    def boom():
        """Test-only fixture route: raises a plain, unhandled exception so
        UnhandledExceptionMiddleware's sanitize-and-log behavior can be
        exercised through a real request. Never registered in production.
        """
        raise ValueError("some internal detail that must not leak")
