import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.errors import AppException
from app.models.session import Session as SessionModel
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.response import APIResponse

router = APIRouter()

SESSION_TTL_DAYS = 7
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


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


def exchange_code_for_tokens(code: str) -> dict:
    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    response.raise_for_status()
    return response.json()


def fetch_google_userinfo(access_token: str) -> dict:
    response = httpx.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return response.json()


@router.get("/google/callback")
def google_callback(code: str, db: Annotated[DBSession, Depends(get_db)]):
    try:
        tokens = exchange_code_for_tokens(code)
        userinfo = fetch_google_userinfo(tokens["access_token"])
    except Exception as e:
        raise AppException(
            status_code=401, code="google_auth_failed", message="Google authentication failed"
        ) from e

    user = db.query(User).filter_by(google_id=userinfo["sub"]).first()
    if user is None:
        user = User(
            google_id=userinfo["sub"],
            email=userinfo["email"],
            full_name=userinfo.get("name"),
            avatar_url=userinfo.get("picture"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    session = SessionModel(
        token=secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=SESSION_TTL_DAYS),
    )
    db.add(session)
    db.commit()

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
    db: Annotated[DBSession, Depends(get_db)],
    session_token: Annotated[str | None, Cookie()] = None,
):
    if session_token is not None:
        db.query(SessionModel).filter_by(token=session_token).delete()
        db.commit()
    response.delete_cookie("session_token")


@router.get("/me", response_model=APIResponse[UserOut])
def get_me(user: Annotated[User, Depends(get_current_user)]):
    return APIResponse.ok(UserOut.model_validate(user, from_attributes=True))
