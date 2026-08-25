def test_response_includes_request_id_header(client):
    response = client.get("/v1/auth/me")

    assert "x-request-id" in response.headers
    assert response.headers["x-request-id"] != ""


def test_client_supplied_request_id_is_echoed_back(client):
    response = client.get("/v1/auth/me", headers={"X-Request-ID": "client-supplied-id-123"})

    assert response.headers["x-request-id"] == "client-supplied-id-123"


def test_two_requests_get_different_generated_request_ids(client):
    first = client.get("/v1/auth/me")
    second = client.get("/v1/auth/me")

    assert first.headers["x-request-id"] != second.headers["x-request-id"]
