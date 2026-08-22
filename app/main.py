from typing import Annotated

from fastapi import Depends, FastAPI

from app.api import auth, sermons
from app.api.deps import get_current_user
from app.errors import AppException, app_exception_handler
from app.models.user import User as UserModel

app = FastAPI(title="Logos")
app.add_exception_handler(AppException, app_exception_handler)  # ty: ignore[invalid-argument-type]
app.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
app.include_router(sermons.router, prefix="/v1/sermons", tags=["sermons"])


@app.get("/v1/_protected_ping", include_in_schema=False)
def protected_ping(user: Annotated[UserModel, Depends(get_current_user)]):
    return {"user_id": str(user.id)}
