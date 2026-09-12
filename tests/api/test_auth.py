from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from app.models.user import User
from app.services.auth_service import AuthService


def _oauth_state(client):
    response = client.get("/v1/auth/google/login", follow_redirects=False)
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def test_login_redirects_to_google_authorization_url(client):
    response = client.get("/v1/auth/google/login", follow_redirects=False)

    assert response.status_code == 307
    assert "accounts.google.com" in response.headers["location"]


def test_callback_with_valid_code_creates_user_and_session(client, db_session):
    with (
        patch("app.api.auth.exchange_code_for_tokens") as mock_exchange,
        patch("app.api.auth.fetch_google_userinfo") as mock_userinfo,
    ):
        mock_exchange.return_value = {"access_token": "fake-access-token"}
        mock_userinfo.return_value = {
            "sub": "google-abc",
            "email": "daniel@example.com",
            "name": "Daniel",
            "picture": "https://pic.example.com/d.jpg",
        }

        state = _oauth_state(client)
        response = client.get(
            f"/v1/auth/google/callback?code=fake-code&state={state}", follow_redirects=False
        )

    assert response.status_code == 307
    assert "session_token" in response.cookies

    user = db_session.query(User).filter_by(google_id="google-abc").first()
    assert user is not None


def test_callback_existing_google_id_does_not_create_second_user(client, db_session):
    with (
        patch("app.api.auth.exchange_code_for_tokens") as mock_exchange,
        patch("app.api.auth.fetch_google_userinfo") as mock_userinfo,
    ):
        mock_exchange.return_value = {"access_token": "fake-access-token"}
        mock_userinfo.return_value = {
            "sub": "google-abc",
            "email": "daniel@example.com",
            "name": "Daniel",
            "picture": None,
        }
        state = _oauth_state(client)
        client.get(f"/v1/auth/google/callback?code=fake-code&state={state}")
        state = _oauth_state(client)
        client.get(f"/v1/auth/google/callback?code=fake-code&state={state}")

    users = db_session.query(User).filter_by(google_id="google-abc").all()
    assert len(users) == 1


def test_callback_with_failed_exchange_returns_error(client, db_session):
    with patch("app.api.auth.exchange_code_for_tokens") as mock_exchange:
        mock_exchange.side_effect = Exception("invalid_grant")

        state = _oauth_state(client)
        response = client.get(f"/v1/auth/google/callback?code=bad-code&state={state}")

    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["error"]["code"] == "google_auth_failed"
    assert db_session.query(User).count() == 0


def test_callback_rejects_invalid_oauth_state(client):
    _oauth_state(client)

    response = client.get("/v1/auth/google/callback?code=fake-code&state=wrong")

    assert response.status_code == 401


def test_mutation_with_session_requires_csrf_token(client, db_session):
    from datetime import UTC, datetime, timedelta

    from app.models.session import Session as SessionModel

    user = User(google_id="csrf-user", email="csrf@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.add(
        SessionModel(
            token=AuthService._hash_session_token("csrf-session"),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    db_session.commit()
    client.cookies.set("session_token", "csrf-session")

    response = client.post("/v1/auth/logout")

    assert response.status_code == 403
