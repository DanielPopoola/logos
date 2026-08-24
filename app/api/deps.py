from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.errors import AppException
from app.models.user import User
from app.repositories.note_repository import NoteRepository
from app.repositories.sermon_repository import SermonRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService, InvalidSessionError, SessionExpiredError
from app.services.note_service import NoteService
from app.services.sermon_service import SermonService


def get_user_repository(db: Annotated[DBSession, Depends(get_db)]) -> UserRepository:
    return UserRepository(db)


def get_session_repository(db: Annotated[DBSession, Depends(get_db)]) -> SessionRepository:
    return SessionRepository(db)


def get_auth_service(
    db: Annotated[DBSession, Depends(get_db)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    sessions: Annotated[SessionRepository, Depends(get_session_repository)],
) -> AuthService:
    return AuthService(db, users, sessions)


def get_current_user(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    session_token: Annotated[str | None, Cookie()] = None,
) -> User:
    if session_token is None:
        raise AppException(status_code=401, code="missing_session", message="Not authenticated")

    try:
        return auth_service.get_authenticated_user(session_token)
    except InvalidSessionError as e:
        raise AppException(status_code=401, code="invalid_session", message="Invalid session") from e
    except SessionExpiredError as e:
        raise AppException(status_code=401, code="session_expired", message="Session has expired") from e


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
