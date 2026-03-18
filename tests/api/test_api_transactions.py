import sqlite3

from database import Database


def _seed_transaction_records():
    db = Database()

    connection = sqlite3.connect("stock_market_database.db")
    cursor = connection.cursor()
    buyer_id = db.create_client(
        "tx_buyer", "tx_buyer@example.com", 1_000_000, "Buyer", "One"
    )
    seller_id = db.create_client(
        "tx_seller", "tx_seller@example.com", 1_000_000, "Seller", "One"
    )
    db.create_owned_stock(seller_id, "OGC", 20)

    cursor.execute("DELETE FROM Transactions;")
    cursor.execute(
        """INSERT INTO Transactions (bidder_id, bid_price, asker_id, ask_price, vol, ticker, time_stamp, transaction_price)\n        VALUES (?, ?, ?, ?, ?, ?, ?, ?);""",
        (buyer_id, 100.0, seller_id, 100.0, 1, "OGC", "2025-01-01 12:00:00", 100.0),
    )
    cursor.execute(
        """INSERT INTO Transactions (bidder_id, bid_price, asker_id, ask_price, vol, ticker, time_stamp, transaction_price)\n        VALUES (?, ?, ?, ?, ?, ?, ?, ?);""",
        (buyer_id, 101.0, seller_id, 101.0, 2, "OGC", "2025-01-02 12:00:00", 101.0),
    )
    connection.commit()
    connection.close()


def test_transactions_endpoint_happy_path_returns_only_public_fields(
    api_client, database_snapshot
):
    _seed_transaction_records()

    response = api_client.get(
        "/api/transactions", params={"ticker": "OGC", "limit": 20}
    )

    assert response.status_code == 200
    body = response.json()

    assert isinstance(body, list)
    assert len(body) == 2
    assert body[0]["price"] > body[1]["price"]
    assert body[0]["ticker"] == "OGC"
    assert body[0]["volume"] == 2
    assert body[0]["timestamp"] == "2025-01-02 12:00:00"
    assert body[1]["timestamp"] == "2025-01-01 12:00:00"
    assert set(body[0].keys()) == {"ticker", "price", "volume", "timestamp"}


def test_transactions_endpoint_rejects_invalid_ticker(api_client, database_snapshot):
    response = api_client.get("/api/transactions", params={"ticker": "ZZZ"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticker 'ZZZ' not found"


def test_transactions_endpoint_rejects_invalid_limit(api_client, database_snapshot):
    response = api_client.get("/api/transactions", params={"ticker": "OGC", "limit": 0})

    assert response.status_code == 400
    assert response.json()["detail"] == "Limit must be a positive integer."
