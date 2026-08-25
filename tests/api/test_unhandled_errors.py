import logging

from fastapi.testclient import TestClient

from app.main import app


def test_unhandled_exception_returns_sanitized_500():
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/v1/_boom")

    body = response.json()
    assert response.status_code == 500
    assert body["success"] is False
    assert body["error"]["code"] == "internal_error"
    assert "some internal detail" not in response.text


def test_unhandled_exception_logs_full_traceback(caplog):
    client = TestClient(app, raise_server_exceptions=False)

    with caplog.at_level(logging.ERROR):
        client.get("/v1/_boom")

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any(r.exc_info and r.exc_info[0] is ValueError for r in error_records)


def test_unhandled_exception_response_includes_request_id():
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/v1/_boom")

    body = response.json()
    assert body["error"]["request_id"] == response.headers["x-request-id"]
