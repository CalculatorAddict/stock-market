from fastapi.testclient import TestClient


def test_get_best_success(api_client: TestClient):
    response = api_client.get("/api/get_best", params={"ticker": "AAPL"})

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"best_bid", "best_ask"}
    assert body["best_bid"] == 0
    assert body["best_ask"] == 0


def test_get_best_invalid_ticker(api_client: TestClient):
    response = api_client.get("/api/get_best", params={"ticker": "ZZZ"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticker 'ZZZ' not found"


def test_get_volume_at_price_rejects_invalid_side(api_client: TestClient):
    response = api_client.get(
        "/api/get_volume_at_price",
        params={"ticker": "AAPL", "side": "zzz", "price": 1.0},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid side. Must be either 'buy' or 'sell'."


def test_root_redirects_to_static_bundle(api_client: TestClient):
    response = api_client.get("/", follow_redirects=False)

    assert response.status_code in {301, 302, 307, 308}
    assert response.headers["location"] == "/app"


def test_static_mount_is_available(api_client: TestClient):
    response = api_client.get("/app")

    assert response.status_code == 200
    assert len(response.text) > 0


def test_place_order_returns_422_for_missing_required_fields(api_client: TestClient):
    response = api_client.post(
        "/api/place_order",
        json={"ticker": "AAPL", "price": 100.0, "volume": 1, "client_user": "tapple"},
    )

    assert response.status_code == 422


def test_market_order_happy_path_no_match_returns_order_id(api_client: TestClient):
    response = api_client.post(
        "/api/market_order",
        json={"ticker": "AAPL", "side": "buy", "volume": 1, "client_user": "tapple"},
    )

    assert response.status_code == 200
    assert isinstance(response.json(), int)
