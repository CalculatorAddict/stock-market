import sqlite3
from datetime import datetime, timezone

from engine.order_book import OrderBook
from models.client import Client
from models.enums import BUY, LIMIT, MARKET, SELL
from models.order import Order

ORDERBOOK_STATE_TABLE = "orderbook_state"


def ensure_orderbook_state_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {ORDERBOOK_STATE_TABLE} (
            order_id INTEGER PRIMARY KEY,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL,
            order_type TEXT NOT NULL,
            price REAL NOT NULL,
            volume INTEGER NOT NULL,
            total_volume INTEGER NOT NULL,
            client_id INTEGER,
            client_username TEXT,
            client_email TEXT,
            timestamp TEXT NOT NULL
        )
        """
    )


def _parse_order_timestamp(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def restore_orderbook_state() -> None:
    connection = sqlite3.connect("stock_market_database.db")
    cursor = connection.cursor()
    ensure_orderbook_state_table(cursor)

    rows = cursor.execute(
        f"""
        SELECT
            order_id, ticker, side, order_type, price, volume,
            total_volume, client_id, client_username, client_email, timestamp
        FROM {ORDERBOOK_STATE_TABLE}
        ORDER BY order_id ASC
        """
    ).fetchall()

    for book in OrderBook._all_books:
        book.bids.clear()
        book.asks.clear()

    if rows:
        max_order_id = max(row[0] for row in rows)
        Order._all_orders = [None] * (max_order_id + 1)
        Order.counter = max_order_id + 1

        for row in rows:
            (
                order_id,
                ticker,
                side,
                order_type,
                price,
                volume,
                total_volume,
                _client_id,
                client_username,
                client_email,
                timestamp,
            ) = row

            book = OrderBook.get_book_by_ticker(ticker)
            if book is None:
                continue

            client = Client.get_client_by_username(client_username)
            if client is None and client_email is not None:
                client = Client.get_client_by_email(client_email)
            if client is None and _client_id is not None:
                client = Client.get_client_by_id(_client_id)
            if client is None:
                continue

            order = Order.__new__(Order)
            order.order_id = order_id
            order.timestamp = _parse_order_timestamp(timestamp)
            order.stock_id = book.stock_id
            order.ticker = ticker
            order.side = BUY if side == BUY.value else SELL
            order.price = price
            order.volume = volume
            order.client_id = client.client_id
            order.client = client
            order.terminated = False
            order.type = MARKET if order_type == MARKET.value else LIMIT
            order._total_volume = total_volume
            order.transaction_ids = []

            Order._all_orders[order_id] = order

            if order.side == BUY:
                book.bids.add(order)
            else:
                book.asks.add(order)
    else:
        Order._all_orders = []
        Order.counter = 0

    cursor.execute(f"DELETE FROM {ORDERBOOK_STATE_TABLE}")
    connection.commit()
    connection.close()


def persist_orderbook_state() -> None:
    connection = sqlite3.connect("stock_market_database.db")
    cursor = connection.cursor()
    ensure_orderbook_state_table(cursor)
    cursor.execute(f"DELETE FROM {ORDERBOOK_STATE_TABLE}")

    for book in OrderBook._all_books:
        for order in book.bids:
            if order.terminated or order.volume <= 0 or order.type is not LIMIT:
                continue
            if order.client is None:
                continue
            cursor.execute(
                f"""
                INSERT INTO {ORDERBOOK_STATE_TABLE}
                    (order_id, ticker, side, order_type, price, volume,
                     total_volume, client_id, client_username, client_email, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.order_id,
                    order.ticker,
                    order.side.value,
                    order.type.value,
                    order.price,
                    order.volume,
                    order._total_volume,
                    order.client_id,
                    order.client.username,
                    order.client.email,
                    order.timestamp.isoformat(),
                ),
            )

        for order in book.asks:
            if order.terminated or order.volume <= 0 or order.type is not LIMIT:
                continue
            if order.client is None:
                continue
            cursor.execute(
                f"""
                INSERT INTO {ORDERBOOK_STATE_TABLE}
                    (order_id, ticker, side, order_type, price, volume,
                     total_volume, client_id, client_username, client_email, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.order_id,
                    order.ticker,
                    order.side.value,
                    order.type.value,
                    order.price,
                    order.volume,
                    order._total_volume,
                    order.client_id,
                    order.client.username,
                    order.client.email,
                    order.timestamp.isoformat(),
                ),
            )

    connection.commit()
    connection.close()
