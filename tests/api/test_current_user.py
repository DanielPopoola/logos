from datetime import UTC, datetime, timedelta

from app.models.session import Session as SessionModel
from app.models.user import User


def _make_user_and_session(db_session, expires_delta=timedelta(days=1)):
    user = User(google_id="g1", email="g1@example.com", full_name="G1")
    db_session.add(user)
    db_session.commit()

    session = SessionModel(
        token="valid-token",
        user_id=user.id,
        expires_at=datetime.now(UTC) + expires_delta,
    )
    db_session.add(session)
    db_session.commit()
    return user, session


def test_valid_session_cookie_resolves_current_user(client, db_session):
    user, _ = _make_user_and_session(db_session)

    response = client.get("/v1/_protected_ping", cookies={"session_token": "valid-token"})

    assert response.status_code == 200
    assert response.json()["user_id"] == str(user.id)


def test_no_cookie_returns_401(client):
    response = client.get("/v1/_protected_ping")
    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["error"]["code"] == "missing_session"


def test_garbage_token_returns_401(client, db_session):
    _make_user_and_session(db_session)
    response = client.get("/v1/_protected_ping", cookies={"session_token": "nonexistent"})
    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["error"]["code"] == "invalid_session"
