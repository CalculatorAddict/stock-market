import json
from uuid import UUID

from fastapi.testclient import TestClient

from engine.tickers import TICKERS

DEFAULT_ACTOR_HEADERS = {
    "X-Actor-User": "tapple",
    "X-Actor-Email": "timcook@aol.com",
}


def test_ws_broadcast_contains_orderbook_snapshot(api_client: TestClient):
    bid_1 = api_client.post(
        "/api/place_order",
        json={
            "ticker": "AAPL",
            "side": "buy",
            "price": 200.0,
            "volume": 1,
            "client_user": "tapple",
        },
    )
    bid_2 = api_client.post(
        "/api/place_order",
        json={
            "ticker": "AAPL",
            "side": "buy",
            "price": 201.0,
            "volume": 1,
            "client_user": "tapple",
        },
    )
    ask_1 = api_client.post(
        "/api/place_order",
        json={
            "ticker": "AAPL",
            "side": "sell",
            "price": 203.0,
            "volume": 1,
            "client_user": "tapple",
        },
    )
    ask_2 = api_client.post(
        "/api/place_order",
        json={
            "ticker": "AAPL",
            "side": "sell",
            "price": 202.0,
            "volume": 1,
            "client_user": "tapple",
        },
    )
    assert bid_1.status_code == 200
    assert bid_2.status_code == 200
    assert ask_1.status_code == 200
    assert ask_2.status_code == 200

    with api_client.websocket_connect("/ws") as websocket:
        payload = json.loads(websocket.receive_text())

    assert payload.keys() == set(TICKERS)
    aapl_snapshot = payload["AAPL"]
    assert aapl_snapshot["ticker"] == "AAPL"
    assert isinstance(aapl_snapshot["all_bids"], list)
    assert isinstance(aapl_snapshot["all_asks"], list)
    assert aapl_snapshot["best_bid"] == 201.0
    assert aapl_snapshot["best_ask"] == 202.0
    assert (
        str(UUID(aapl_snapshot["all_bids"][0]["order_id"]))
        == aapl_snapshot["all_bids"][0]["order_id"]
    )
    assert (
        str(UUID(aapl_snapshot["all_asks"][0]["order_id"]))
        == aapl_snapshot["all_asks"][0]["order_id"]
    )
    assert set(aapl_snapshot.keys()) == {
        "ticker",
        "best_bid",
        "best_ask",
        "all_bids",
        "all_asks",
        "last_price",
        "last_timestamp",
        "server_time",
        "pnl",
    }


def test_orderbook_state_persists_across_testclient_restarts(
    app_module, database_snapshot
):
    with TestClient(app_module.app, headers=DEFAULT_ACTOR_HEADERS) as first_client:
        response = first_client.post(
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
        order_id = response.json()

    with TestClient(app_module.app, headers=DEFAULT_ACTOR_HEADERS) as restarted_client:
        response = restarted_client.get("/api/get_all_bids", params={"ticker": "AAPL"})

    assert response.status_code == 200
    assert any(
        order["order_id"] == order_id
        and order["price"] == 250.0
        and order["volume"] == 1
        for order in response.json()
    )
