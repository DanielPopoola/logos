def test_error_response_request_id_matches_header(client):
    response = client.get("/v1/auth/me")

    body = response.json()
    assert response.status_code == 401
    assert body["error"]["request_id"] == response.headers["x-request-id"]


def test_error_response_request_id_matches_client_supplied_header(client):
    response = client.get("/v1/auth/me", headers={"X-Request-ID": "trace-abc-123"})

    body = response.json()
    assert body["error"]["request_id"] == "trace-abc-123"
    assert response.headers["x-request-id"] == "trace-abc-123"
