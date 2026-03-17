from uuid import UUID


def test_add_new_client_returns_public_uuid_client_id(api_client):
    response = api_client.post(
        "/api/add_new_client",
        json={
            "email": "uuid-client@example.com",
            "first_name": "Uuid",
            "last_name": "Client",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert str(UUID(body["client_id"])) == body["client_id"]
    assert body["username"] == "uuid-client@example.com"
    assert body["email"] == "uuid-client@example.com"
    assert "password" not in body


def test_get_client_by_email_returns_public_payload(api_client):
    create_response = api_client.post(
        "/api/add_new_client",
        json={
            "email": "lookup-client@example.com",
            "first_name": "Lookup",
            "last_name": "Client",
        },
    )
    created = create_response.json()

    response = api_client.get(
        "/api/get_client_by_email", params={"email": "lookup-client@example.com"}
    )
    assert response.status_code == 200

    body = response.json()
    assert body["client_id"] == created["client_id"]
    assert str(UUID(body["client_id"])) == body["client_id"]
    assert body["username"] == "lookup-client@example.com"
    assert "password" not in body


def test_get_client_by_email_missing_returns_404(api_client):
    response = api_client.get(
        "/api/get_client_by_email", params={"email": "missing@example.com"}
    )
    assert response.status_code == 404
    assert (
        response.json()["detail"] == "Client with email missing@example.com not found."
    )
