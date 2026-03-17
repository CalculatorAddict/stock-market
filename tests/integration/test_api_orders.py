from fastapi.testclient import TestClient


def test_place_order_happy_path(api_client: TestClient):
    response = api_client.post(
        "/api/place_order",
        json={
            "ticker": "AAPL",
            "side": "buy",
            "price": 250.0,
            "volume": 1,
            "client_user": "tapple",
        },
    )
    assert response.status_code == 200
    assert isinstance(response.json(), int)


def test_place_order_invalid_ticker(api_client: TestClient):
    response = api_client.post(
        "/api/place_order",
        json={
            "ticker": "ZZZ",
            "side": "buy",
            "price": 250.0,
            "volume": 1,
            "client_user": "tapple",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Ticker 'ZZZ' not found"


def test_place_order_invalid_side(api_client: TestClient):
    response = api_client.post(
        "/api/place_order",
        json={
            "ticker": "AAPL",
            "side": "up",
            "price": 250.0,
            "volume": 1,
            "client_user": "tapple",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid side. Must be either 'buy' or 'sell'."


def test_place_order_rejects_non_positive_price(api_client: TestClient):
    response = api_client.post(
        "/api/place_order",
        json={
            "ticker": "AAPL",
            "side": "buy",
            "price": 0.0,
            "volume": 1,
            "client_user": "tapple",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Limit order price must be greater than zero."


def test_market_order_invalid_volume(api_client: TestClient):
    response = api_client.post(
        "/api/market_order",
        json={
            "ticker": "AAPL",
            "side": "buy",
            "volume": 0,
            "client_user": "tapple",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Market order volume must be greater than zero."


def test_cancel_order_happy_path_and_structure(api_client: TestClient):
    order_response = api_client.post(
        "/api/place_order",
        json={
            "ticker": "AAPL",
            "side": "buy",
            "price": 251.0,
            "volume": 1,
            "client_user": "tapple",
        },
    )
    order_id = order_response.json()

    response = api_client.post("/api/cancel_order", json={"order_id": order_id})
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "success"
    assert body["order_id"] == order_id
    assert "message" in body


def test_cancel_order_not_found(api_client: TestClient):
    response = api_client.post("/api/cancel_order", json={"order_id": 999_999})
    assert response.status_code == 404
    assert response.json()["detail"] == "Order 999999 does not exist."


def test_edit_order_happy_path_and_structure(api_client: TestClient):
    order_response = api_client.post(
        "/api/place_order",
        json={
            "ticker": "AAPL",
            "side": "buy",
            "price": 252.0,
            "volume": 1,
            "client_user": "tapple",
        },
    )
    order_id = order_response.json()

    response = api_client.post(
        "/api/edit_order",
        json={"order_id": order_id, "price": 253.0, "volume": 2},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "success"
    assert body["order_id"] == order_id
    assert body["delta_volume"] == 1
    assert "message" in body


def test_edit_order_invalid_price_or_volume(api_client: TestClient):
    order_response = api_client.post(
        "/api/place_order",
        json={
            "ticker": "AAPL",
            "side": "buy",
            "price": 254.0,
            "volume": 1,
            "client_user": "tapple",
        },
    )
    order_id = order_response.json()

    response = api_client.post(
        "/api/edit_order",
        json={"order_id": order_id, "price": -1.0, "volume": 1},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Order price must be greater than zero."
