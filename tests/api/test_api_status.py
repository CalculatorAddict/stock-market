import uuid


def test_order_status_open(api_client):
    order_response = api_client.post(
        "/api/place_order",
        json={
            "ticker": "OGC",
            "side": "buy",
            "price": 210.0,
            "volume": 2,
            "client_user": "amorgan",
        },
    )
    order_id = order_response.json()

    response = api_client.get("/api/order_status", params={"order_id": order_id})
    assert response.status_code == 200
    body = response.json()

    assert body["order_id"] == order_id
    assert body["status"] == "open"
    assert body["executed_volume"] == 0
    assert body["remaining_volume"] == 2
    assert body["terminated"] is False


def test_order_status_partially_filled(api_client):
    ask_response = api_client.post(
        "/api/place_order",
        headers={"X-Actor-User": "jlee", "X-Actor-Email": "jordan.lee@demo.local"},
        json={
            "ticker": "OGC",
            "side": "sell",
            "price": 100.0,
            "volume": 5,
            "client_user": "jlee",
        },
    )
    ask_order_id = ask_response.json()

    buy_response = api_client.post(
        "/api/place_order",
        json={
            "ticker": "OGC",
            "side": "buy",
            "price": 100.0,
            "volume": 2,
            "client_user": "amorgan",
        },
    )
    assert buy_response.status_code == 200

    response = api_client.get(
        "/api/order_status",
        params={"order_id": ask_order_id},
        headers={"X-Actor-User": "jlee", "X-Actor-Email": "jordan.lee@demo.local"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "partially_filled"
    assert body["total_volume"] == 5
    assert body["executed_volume"] == 2
    assert body["remaining_volume"] == 3
    assert body["terminated"] is False


def test_order_status_filled(api_client):
    buy_response = api_client.post(
        "/api/place_order",
        json={
            "ticker": "OGC",
            "side": "buy",
            "price": 120.0,
            "volume": 2,
            "client_user": "amorgan",
        },
    )
    buy_order_id = buy_response.json()

    sell_response = api_client.post(
        "/api/place_order",
        headers={"X-Actor-User": "jlee", "X-Actor-Email": "jordan.lee@demo.local"},
        json={
            "ticker": "OGC",
            "side": "sell",
            "price": 120.0,
            "volume": 2,
            "client_user": "jlee",
        },
    )
    assert sell_response.status_code == 200

    response = api_client.get("/api/order_status", params={"order_id": buy_order_id})
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "filled"
    assert body["executed_volume"] == 2
    assert body["remaining_volume"] == 0
    assert body["terminated"] is True


def test_order_status_canceled(api_client):
    order_response = api_client.post(
        "/api/place_order",
        json={
            "ticker": "OGC",
            "side": "buy",
            "price": 130.0,
            "volume": 2,
            "client_user": "amorgan",
        },
    )
    order_id = order_response.json()

    cancel_response = api_client.post("/api/cancel_order", json={"order_id": order_id})
    assert cancel_response.status_code == 200

    response = api_client.get("/api/order_status", params={"order_id": order_id})
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "canceled"
    assert body["remaining_volume"] > 0
    assert body["terminated"] is True


def test_order_status_invalid_uuid_and_missing_order(api_client):
    invalid = api_client.get("/api/order_status", params={"order_id": "not-a-uuid"})
    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "Invalid order id format. Must be a UUID string."

    missing_uuid = str(uuid.uuid4())
    missing = api_client.get("/api/order_status", params={"order_id": missing_uuid})
    assert missing.status_code == 404
    assert missing.json()["detail"] == f"Order {missing_uuid} does not exist."


def test_order_status_rejects_mismatched_actor(api_client):
    order_response = api_client.post(
        "/api/place_order",
        headers={"X-Actor-User": "jlee", "X-Actor-Email": "jordan.lee@demo.local"},
        json={
            "ticker": "OGC",
            "side": "sell",
            "price": 200.0,
            "volume": 1,
            "client_user": "jlee",
        },
    )
    jlee_order_id = order_response.json()

    response = api_client.get("/api/order_status", params={"order_id": jlee_order_id})
    assert response.status_code == 403
    assert response.json()["detail"] == "Actor username does not match target user."


def test_open_orders_returns_only_authenticated_active_orders(api_client):
    open_order_response = api_client.post(
        "/api/place_order",
        json={
            "ticker": "OGC",
            "side": "buy",
            "price": 90.0,
            "volume": 2,
            "client_user": "amorgan",
        },
    )
    open_order_id = open_order_response.json()

    canceled_order_response = api_client.post(
        "/api/place_order",
        json={
            "ticker": "OGC",
            "side": "buy",
            "price": 89.0,
            "volume": 1,
            "client_user": "amorgan",
        },
    )
    canceled_order_id = canceled_order_response.json()
    cancel_response = api_client.post(
        "/api/cancel_order", json={"order_id": canceled_order_id}
    )
    assert cancel_response.status_code == 200

    filled_order_response = api_client.post(
        "/api/place_order",
        json={
            "ticker": "OGC",
            "side": "buy",
            "price": 120.0,
            "volume": 1,
            "client_user": "amorgan",
        },
    )
    filled_order_id = filled_order_response.json()
    match_response = api_client.post(
        "/api/place_order",
        headers={"X-Actor-User": "jlee", "X-Actor-Email": "jordan.lee@demo.local"},
        json={
            "ticker": "OGC",
            "side": "sell",
            "price": 120.0,
            "volume": 1,
            "client_user": "jlee",
        },
    )
    assert match_response.status_code == 200

    foreign_order_response = api_client.post(
        "/api/place_order",
        headers={"X-Actor-User": "jlee", "X-Actor-Email": "jordan.lee@demo.local"},
        json={
            "ticker": "OGC",
            "side": "sell",
            "price": 200.0,
            "volume": 1,
            "client_user": "jlee",
        },
    )
    foreign_order_id = foreign_order_response.json()

    response = api_client.get("/api/open_orders")
    assert response.status_code == 200
    assert response.json() == [open_order_id]
    assert canceled_order_id not in response.json()
    assert filled_order_id not in response.json()
    assert foreign_order_id not in response.json()
