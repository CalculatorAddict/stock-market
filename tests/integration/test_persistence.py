import sqlite3
from uuid import UUID

from fastapi.testclient import TestClient

from app.persistence import ORDERBOOK_STATE_TABLE


def _fetch_persisted_rows():
    connection = sqlite3.connect("stock_market_database.db")
    cursor = connection.cursor()
    cursor.execute(
        f"""
        SELECT order_id, ticker, side, order_type, price, volume
        FROM {ORDERBOOK_STATE_TABLE}
        ORDER BY order_id ASC
        """
    )
    rows = cursor.fetchall()
    connection.close()
    return rows


def test_shutdown_persists_open_limit_order_then_startup_restores_and_clears_state(
    app_module,
):
    with TestClient(app_module.app) as client:
        response = client.post(
            "/api/place_order",
            json={
                "ticker": "AAPL",
                "side": "buy",
                "price": 333.0,
                "volume": 2,
                "client_user": "tapple",
            },
        )
        assert response.status_code == 200
        order_id = response.json()
        assert str(UUID(order_id)) == order_id

    rows_after_shutdown = _fetch_persisted_rows()
    assert len(rows_after_shutdown) == 1
    persisted_order_id, ticker, side, order_type, price, volume = rows_after_shutdown[0]
    assert isinstance(persisted_order_id, int)
    assert (ticker, side, order_type, price, volume) == (
        "AAPL",
        "buy",
        "limit",
        333.0,
        2,
    )

    with TestClient(app_module.app) as restarted_client:
        response = restarted_client.get("/api/get_all_bids", params={"ticker": "AAPL"})
        assert response.status_code == 200
        assert any(
            order["order_id"] == order_id
            and order["price"] == 333.0
            and order["volume"] == 2
            for order in response.json()
        )
        # Startup restore should consume persisted state rows.
        assert _fetch_persisted_rows() == []

    # On shutdown, open orders are persisted again.
    rows_after_second_shutdown = _fetch_persisted_rows()
    assert len(rows_after_second_shutdown) == 1
    _, ticker, side, order_type, price, volume = rows_after_second_shutdown[0]
    assert (ticker, side, order_type, price, volume) == (
        "AAPL",
        "buy",
        "limit",
        333.0,
        2,
    )


def test_shutdown_does_not_persist_canceled_orders(app_module):
    with TestClient(app_module.app) as client:
        response = client.post(
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

        cancel_response = client.post("/api/cancel_order", json={"order_id": order_id})
        assert cancel_response.status_code == 200

    rows_after_shutdown = _fetch_persisted_rows()
    assert rows_after_shutdown == []
