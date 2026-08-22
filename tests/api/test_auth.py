from unittest.mock import patch

from app.models.user import User


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

        response = client.get("/v1/auth/google/callback?code=fake-code", follow_redirects=False)

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
        client.get("/v1/auth/google/callback?code=fake-code")
        client.get("/v1/auth/google/callback?code=fake-code")

    users = db_session.query(User).filter_by(google_id="google-abc").all()
    assert len(users) == 1


def test_callback_with_failed_exchange_returns_error(client, db_session):
    with patch("app.api.auth.exchange_code_for_tokens") as mock_exchange:
        mock_exchange.side_effect = Exception("invalid_grant")

        response = client.get("/v1/auth/google/callback?code=bad-code")

    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["error"]["code"] == "google_auth_failed"
    assert db_session.query(User).count() == 0
