import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_current_user
from app.database import get_db
from app.errors import AppException
from app.models.session import Session as SessionModel
from app.models.user import User
from app.schemas.auth import GoogleAuthRequest, GoogleAuthResponse, UserOut
from app.schemas.response import APIResponse

router = APIRouter()

SESSION_TTL_DAYS = 7


def verify_google_token(token: str) -> dict:
    return google_id_token.verify_oauth2_token(token, google_requests.Request())


@router.post("/google", response_model=APIResponse[GoogleAuthResponse])
def google_auth(
    payload: GoogleAuthRequest, response: Response, db: Annotated[DBSession, Depends(get_db)]
):
    try:
        claims = verify_google_token(payload.id_token)
    except ValueError as e:
        raise AppException(
            status_code=401, code="invalid_google_token", message="Invalid Google token"
        ) from e

    user = db.query(User).filter_by(google_id=claims["sub"]).first()
    if user is None:
        user = User(
            google_id=claims["sub"],
            email=claims["email"],
            full_name=claims.get("name"),
            avatar_url=claims.get("picture"),
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

    response.set_cookie(
        key="session_token",
        value=session.token,
        httponly=True,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
    )

    return APIResponse.ok(
        GoogleAuthResponse(
            user=UserOut.model_validate(user, from_attributes=True),
            session_token=session.token,
        )
    )


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
