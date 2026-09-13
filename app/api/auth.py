import hashlib
import hmac
import logging
import secrets
import time
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import get_auth_service, get_current_user
from app.auth.google_client import exchange_code_for_tokens, fetch_google_userinfo
from app.config import settings
from app.errors import AppException
from app.middleware.security import CSRF_COOKIE_NAME
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.response import APIResponse
from app.services.auth_service import SESSION_TTL_DAYS, AuthService

router = APIRouter()
logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_STATE_COOKIE = "oauth_state"
OAUTH_STATE_TTL_SECONDS = 600


def _oauth_state_value() -> str:
    nonce = secrets.token_urlsafe(32)
    issued_at = str(int(time.time()))
    value = f"{issued_at}.{nonce}"
    signature = hmac.new(
        settings.google_client_secret.encode(), value.encode(), hashlib.sha256
    ).hexdigest()
    return f"{value}.{signature}"


def _valid_oauth_state(state: str | None, cookie_state: str | None) -> bool:
    if not state or not cookie_state or not hmac.compare_digest(state, cookie_state):
        return False
    parts = state.split(".")
    if len(parts) != 3:
        return False
    issued_at, nonce, signature = parts
    value = f"{issued_at}.{nonce}"
    expected = hmac.new(
        settings.google_client_secret.encode(), value.encode(), hashlib.sha256
    ).hexdigest()
    try:
        age = time.time() - int(issued_at)
    except ValueError:
        return False
    return 0 <= age <= OAUTH_STATE_TTL_SECONDS and hmac.compare_digest(signature, expected)


@router.get("/google/login")
def google_login():
    logger.info("Authentication login initiated", extra={"auth_provider": "google"})
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    state = _oauth_state_value()
    params["state"] = state
    url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    redirect = RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    redirect.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        max_age=OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        secure=settings.environment not in ("test", "development"),
        samesite="lax",
        path="/v1/auth/google",
    )
    return redirect


@router.get("/google/callback")
def google_callback(
    code: str,
    state: str,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    oauth_state: Annotated[str | None, Cookie(alias=OAUTH_STATE_COOKIE)] = None,
):
    if not _valid_oauth_state(state, oauth_state):
        logger.warning("Authentication callback rejected", extra={"auth_reason": "invalid_state"})
        raise AppException(
            status_code=401,
            code="google_auth_failed",
            message="Google authentication failed",
        )

    try:
        tokens = exchange_code_for_tokens(code)
        userinfo = fetch_google_userinfo(tokens["access_token"])
    except Exception as e:
        logger.warning(
            "Authentication callback failed",
            exc_info=e,
            extra={"auth_provider": "google", "auth_event": "login_failure"},
        )
        raise AppException(
            status_code=401, code="google_auth_failed", message="Google authentication failed"
        ) from e

    user = auth_service.get_or_create_user(userinfo)
    session = auth_service.create_session(user)
    logger.info(
        "Authentication succeeded",
        extra={"auth_provider": "google", "auth_event": "login_success", "user_id": str(user.id)},
    )

    redirect = RedirectResponse(
        url=f"{settings.frontend_url}/library", status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )
    redirect.set_cookie(
        key="session_token",
        value=session.token,
        httponly=True,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
        samesite="none" if settings.environment not in ("test", "development") else "lax",
        secure=settings.environment not in ("test", "development"),
    )
    redirect.delete_cookie(OAUTH_STATE_COOKIE, path="/v1/auth/google")
    return redirect


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    session_token: Annotated[str | None, Cookie()] = None,
):
    if session_token is not None:
        auth_service.logout(session_token)
        logger.info("Authentication logout completed", extra={"auth_event": "logout"})
    else:
        logger.info("Authentication logout requested without session")
    response.delete_cookie(
        "session_token",
        samesite="none" if settings.environment not in ("test", "development") else "lax",
        secure=settings.environment not in ("test", "development"),
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path="/",
        samesite="none" if settings.environment not in ("test", "development") else "lax",
        secure=settings.environment not in ("test", "development"),
    )


@router.get("/me", response_model=APIResponse[UserOut])
def get_me(user: Annotated[User, Depends(get_current_user)]):
    return APIResponse.ok(UserOut.model_validate(user, from_attributes=True))
