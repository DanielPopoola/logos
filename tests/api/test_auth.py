from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.models.session import Session as SessionModel
from app.models.user import User


def _make_user_and_session(db_session, expires_delta=timedelta(days=1)):
    user = User(google_id="g2", email="g2@example.com", full_name="G2")
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


def test_valid_token_new_user_creates_user_and_returns_session(client, db_session):
    with patch("app.api.auth.verify_google_token") as mock_verify:
        mock_verify.return_value = {
            "sub": "google-abc",
            "email": "daniel@example.com",
            "name": "Daniel",
            "picture": "https://pic.example.com/d.jpg",
        }
        response = client.post("/v1/auth/google", json={"id_token": "fake-token"})

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["user"]["email"] == "daniel@example.com"
    assert "session_token" in body["data"]

    user = db_session.query(User).filter_by(google_id="google-abc").first()
    assert user is not None


def test_existing_google_id_does_not_create_second_user(client, db_session):
    with patch("app.api.auth.verify_google_token") as mock_verify:
        mock_verify.return_value = {
            "sub": "google-abc",
            "email": "daniel@example.com",
            "name": "Daniel",
            "picture": None,
        }
        client.post("/v1/auth/google", json={"id_token": "fake-token"})
        client.post("/v1/auth/google", json={"id_token": "fake-token"})

    users = db_session.query(User).filter_by(google_id="google-abc").all()
    assert len(users) == 1


def test_invalid_token_returns_401_and_creates_nothing(client, db_session):
    with patch("app.api.auth.verify_google_token") as mock_verify:
        mock_verify.side_effect = ValueError("invalid token")
        response = client.post("/v1/auth/google", json={"id_token": "garbage"})

    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["error"]["code"] == "invalid_google_token"
    assert "request_id" in body["error"]

    assert db_session.query(User).count() == 0
    assert db_session.query(SessionModel).count() == 0


def test_logout_deletes_session_and_stale_cookie_then_returns_401(client, db_session):
    _make_user_and_session(db_session)

    logout_response = client.post("/v1/auth/logout", cookies={"session_token": "valid-token"})
    assert logout_response.status_code == 204

    assert db_session.query(SessionModel).filter_by(token="valid-token").first() is None

    followup = client.get("/v1/_protected_ping", cookies={"session_token": "valid-token"})
    assert followup.status_code == 401


def test_me_returns_authenticated_users_own_data(client, db_session):
    user, _ = _make_user_and_session(db_session)

    response = client.get("/v1/auth/me", cookies={"session_token": "valid-token"})

    body = response.json()
    assert response.status_code == 200
    assert body["data"]["email"] == "g2@example.com"


def test_me_returns_401_when_unauthenticated(client):
    response = client.get("/v1/auth/me")
    assert response.status_code == 401


def test_expired_session_is_treated_as_invalid(client, db_session):
    _make_user_and_session(db_session, expires_delta=timedelta(days=-1))

    response = client.get("/v1/_protected_ping", cookies={"session_token": "valid-token"})

    body = response.json()
    assert response.status_code == 401
    assert body["error"]["code"] == "session_expired"
