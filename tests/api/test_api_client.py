from uuid import UUID


def test_add_new_client_returns_public_uuid_client_id(api_client):
    response = api_client.post(
        "/api/add_new_client",
        headers={"X-Actor-Email": "uuid-client@example.com"},
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
        headers={"X-Actor-Email": "lookup-client@example.com"},
        json={
            "email": "lookup-client@example.com",
            "first_name": "Lookup",
            "last_name": "Client",
        },
    )
    created = create_response.json()

    response = api_client.get(
        "/api/get_client_by_email",
        params={"email": "lookup-client@example.com"},
        headers={"X-Actor-Email": "lookup-client@example.com"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["client_id"] == created["client_id"]
    assert str(UUID(body["client_id"])) == body["client_id"]
    assert body["username"] == "lookup-client@example.com"
    assert "password" not in body


def test_get_client_by_email_missing_returns_404(api_client):
    response = api_client.get(
        "/api/get_client_by_email",
        params={"email": "missing@example.com"},
        headers={"X-Actor-Email": "missing@example.com"},
    )
    assert response.status_code == 404
    assert (
        response.json()["detail"] == "Client with email missing@example.com not found."
    )


def test_get_client_by_email_rejects_mismatched_actor_email(api_client):
    response = api_client.get(
        "/api/get_client_by_email",
        params={"email": "lookup-client@example.com"},
        headers={"X-Actor-Email": "other@example.com"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Actor email does not match target user."


def test_client_info_token_returns_signed_subscription_token(api_client):
    response = api_client.get(
        "/api/client_info_token",
        params={"email": "alex.morgan@demo.local"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "alex.morgan@demo.local"
    assert isinstance(body["token"], str)
    assert "." in body["token"]


def test_client_info_token_rejects_mismatched_actor(api_client):
    response = api_client.get(
        "/api/client_info_token",
        params={"email": "alex.morgan@demo.local"},
        headers={"X-Actor-Email": "other@example.com"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Actor email does not match target user."
