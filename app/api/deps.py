from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.errors import AppException
from app.models.session import Session as SessionModel
from app.models.user import User
from app.repositories.note_repository import NoteRepository
from app.repositories.sermon_repository import SermonRepository
from app.services.note_service import NoteService
from app.services.sermon_service import SermonService


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


def get_note_repository(db: Annotated[DBSession, Depends(get_db)]) -> NoteRepository:
    return NoteRepository(db)


def get_sermon_repository(db: Annotated[DBSession, Depends(get_db)]) -> SermonRepository:
    return SermonRepository(db)


def get_note_service(
    db: Annotated[DBSession, Depends(get_db)],
    notes: Annotated[NoteRepository, Depends(get_note_repository)],
    sermons: Annotated[SermonRepository, Depends(get_sermon_repository)],
) -> NoteService:
    return NoteService(db, notes, sermons)


def get_sermon_service(
    db: Annotated[DBSession, Depends(get_db)],
    sermons: Annotated[SermonRepository, Depends(get_sermon_repository)],
    notes: Annotated[NoteRepository, Depends(get_note_repository)],
) -> SermonService:
    return SermonService(db, sermons, notes)
