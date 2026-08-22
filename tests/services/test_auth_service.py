from datetime import UTC, datetime

from app.models.session import Session as SessionModel
from app.models.user import User
from app.services.auth_service import create_session, get_or_create_user

GOOGLE_USERINFO = {
    "sub": "google-abc",
    "email": "daniel@example.com",
    "name": "Daniel",
    "picture": "https://pic.example.com/d.jpg",
}


def test_get_or_create_user_creates_new_user_for_unseen_google_id(db_session):
    user = get_or_create_user(db_session, GOOGLE_USERINFO)

    assert user.google_id == "google-abc"
    assert user.email == "daniel@example.com"
    assert db_session.query(User).filter_by(google_id="google-abc").count() == 1


def test_get_or_create_user_returns_existing_user_without_duplicating(db_session):
    first = get_or_create_user(db_session, GOOGLE_USERINFO)
    second = get_or_create_user(db_session, GOOGLE_USERINFO)

    assert first.id == second.id
    assert db_session.query(User).filter_by(google_id="google-abc").count() == 1


def test_get_or_create_user_handles_missing_picture(db_session):
    userinfo = {**GOOGLE_USERINFO, "picture": None}

    user = get_or_create_user(db_session, userinfo)

    assert user.avatar_url is None


def test_create_session_persists_token_bound_to_user(db_session):
    user = get_or_create_user(db_session, GOOGLE_USERINFO)

    session = create_session(db_session, user)

    stored = db_session.query(SessionModel).filter_by(token=session.token).one()
    assert stored.user_id == user.id
    assert stored.expires_at > datetime.now(UTC)
