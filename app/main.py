from typing import Annotated

from fastapi import Depends, FastAPI

from app.api import ask, auth, notes, search, sermons
from app.api.deps import get_current_user
from app.config import settings
from app.errors import AppException, app_exception_handler
from app.middleware.request_id import RequestIDMiddleware
from app.models.user import User as UserModel

app = FastAPI(title="Logos")
app.add_middleware(RequestIDMiddleware)
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
