from unittest.mock import MagicMock

from app.database import get_db
from app.main import app


def test_healthz_returns_200_when_db_reachable(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_healthz_returns_503_when_db_unreachable(client, db_session):
    def broken_get_db():
        broken_session = MagicMock()
        broken_session.execute.side_effect = Exception("connection refused")
        yield broken_session

    app.dependency_overrides[get_db] = broken_get_db
    try:
        response = client.get("/healthz")
    finally:
        app.dependency_overrides[get_db] = lambda: iter([db_session])

    assert response.status_code == 503
    assert response.json()["status"] == "error"


def test_healthz_requires_no_authentication(client):
    response = client.get("/healthz")

    assert response.status_code != 401
