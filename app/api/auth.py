from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import get_auth_service, get_current_user
from app.auth.google_client import exchange_code_for_tokens, fetch_google_userinfo
from app.config import settings
from app.errors import AppException
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.response import APIResponse
from app.services.auth_service import SESSION_TTL_DAYS, AuthService

router = APIRouter()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


@router.get("/google/login")
def google_login():
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/google/callback")
def google_callback(
    code: str,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    try:
        tokens = exchange_code_for_tokens(code)
        userinfo = fetch_google_userinfo(tokens["access_token"])
    except Exception as e:
        raise AppException(
            status_code=401, code="google_auth_failed", message="Google authentication failed"
        ) from e

    user = auth_service.get_or_create_user(userinfo)
    session = auth_service.create_session(user)

    redirect = RedirectResponse(url="/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    redirect.set_cookie(
        key="session_token",
        value=session.token,
        httponly=True,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
    )
    return redirect


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    session_token: Annotated[str | None, Cookie()] = None,
):
    if session_token is not None:
        auth_service.logout(session_token)
    response.delete_cookie("session_token")


@router.get("/me", response_model=APIResponse[UserOut])
def get_me(user: Annotated[User, Depends(get_current_user)]):
    return APIResponse.ok(UserOut.model_validate(user, from_attributes=True))
