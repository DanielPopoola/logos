from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.errors import AppException
from app.models.session import Session as SessionModel
from app.models.user import User


def get_current_user(
    db: Annotated[DBSession, Depends(get_db)],
    session_token: Annotated[str | None, Cookie()] = None,
) -> User:
    if session_token is None:
        raise AppException(status_code=401, code="missing_session", message="Not authenticated")

    session = db.query(SessionModel).filter_by(token=session_token).first()
    if session is None:
        raise AppException(status_code=401, code="invalid_session", message="Invalid session")

    if session.expires_at < datetime.now(UTC):
        raise AppException(status_code=401, code="session_expired", message="Session has expired")

    return db.query(User).filter_by(id=session.user_id).first()  # ty: ignore[invalid-return-type]
