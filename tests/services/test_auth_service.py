from datetime import UTC, datetime, timedelta

import pytest

from app.models.session import Session as SessionModel
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService, InvalidSessionError, SessionExpiredError

GOOGLE_USERINFO = {
    "sub": "google-abc",
    "email": "daniel@example.com",
    "name": "Daniel",
    "picture": "https://pic.example.com/d.jpg",
}


def _auth_service(db_session) -> AuthService:
    return AuthService(db_session, UserRepository(db_session), SessionRepository(db_session))


# --- get_or_create_user -------------------------------------------------


def test_get_or_create_user_creates_new_user_for_unseen_google_id(db_session):
    service = _auth_service(db_session)

    user = service.get_or_create_user(GOOGLE_USERINFO)

    assert user.google_id == "google-abc"
    assert user.email == "daniel@example.com"
    assert db_session.query(User).filter_by(google_id="google-abc").count() == 1


def test_get_or_create_user_returns_existing_user_without_duplicating(db_session):
    service = _auth_service(db_session)

    first = service.get_or_create_user(GOOGLE_USERINFO)
    second = service.get_or_create_user(GOOGLE_USERINFO)

    assert first.id == second.id
    assert db_session.query(User).filter_by(google_id="google-abc").count() == 1


def test_get_or_create_user_handles_missing_picture(db_session):
    service = _auth_service(db_session)
    userinfo = {**GOOGLE_USERINFO, "picture": None}

    user = service.get_or_create_user(userinfo)

    assert user.avatar_url is None


# --- create_session -------------------------------------------------------


def test_create_session_persists_token_bound_to_user(db_session):
    service = _auth_service(db_session)
    user = service.get_or_create_user(GOOGLE_USERINFO)

    session = service.create_session(user)

    stored = db_session.query(SessionModel).filter_by(token=session.token).one()
    assert stored.user_id == user.id
    assert stored.expires_at > datetime.now(UTC)


# --- get_authenticated_user -------------------------------------------------


def test_get_authenticated_user_returns_user_for_valid_session(db_session):
    service = _auth_service(db_session)
    user = service.get_or_create_user(GOOGLE_USERINFO)
    session = service.create_session(user)

    resolved = service.get_authenticated_user(session.token)

    assert resolved.id == user.id


def test_get_authenticated_user_raises_invalid_for_unknown_token(db_session):
    service = _auth_service(db_session)

    with pytest.raises(InvalidSessionError):
        service.get_authenticated_user("nonexistent-token")


def test_get_authenticated_user_raises_expired_for_stale_session(db_session):
    service = _auth_service(db_session)
    user = service.get_or_create_user(GOOGLE_USERINFO)
    db_session.add(
        SessionModel(
            token="stale-token",
            user_id=user.id,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    db_session.commit()

    with pytest.raises(SessionExpiredError):
        service.get_authenticated_user("stale-token")


# --- logout -----------------------------------------------------------------


def test_logout_deletes_session(db_session):
    service = _auth_service(db_session)
    user = service.get_or_create_user(GOOGLE_USERINFO)
    session = service.create_session(user)

    service.logout(session.token)

    assert db_session.query(SessionModel).filter_by(token=session.token).count() == 0


def test_logout_is_idempotent_for_unknown_token(db_session):
    service = _auth_service(db_session)

    service.logout("never-existed")  # should not raise
