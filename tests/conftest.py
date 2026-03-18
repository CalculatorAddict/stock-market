from importlib import import_module, reload
from pathlib import Path
import os
import sqlite3
import shutil
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(os.path.dirname(os.path.abspath(__file__))).resolve().parent
BASE_DB_PATH = ROOT_DIR / "stock_market_database.db"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.order_book import OrderBook
from engine.portfolio_value import PortfolioValue
from app.price_history import clear_history_state
from models.client import Client
from models.order import Order


def _restore_database_from_backup(db_path: Path, backup: Path) -> None:
    shutil.copy2(backup, db_path)


def _clear_orderbook_state_table() -> None:
    connection = sqlite3.connect("stock_market_database.db")
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orderbook_state (
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
    cursor.execute("DELETE FROM orderbook_state;")
    connection.commit()
    connection.close()


@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    db_path = tmp_path / "stock_market_database.db"
    if BASE_DB_PATH.exists():
        shutil.copy2(BASE_DB_PATH, db_path)
    else:
        sqlite3.connect(db_path).close()
    return db_path


@pytest.fixture(autouse=True)
def reset_domain_state(monkeypatch: pytest.MonkeyPatch, test_db_path: Path):
    """Reset shared domain state before each test for isolation."""
    original_connect = sqlite3.connect

    def _connect(database, *args, **kwargs):
        if isinstance(database, (str, os.PathLike)):
            if Path(database).name == "stock_market_database.db":
                database = str(test_db_path)
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", _connect)

    OrderBook._all_books.clear()
    OrderBook._tickers.clear()
    OrderBook.counter = 0

    Order._all_orders.clear()
    Order.counter = 0

    Client._all_clients.clear()
    Client._clients_by_username.clear()
    Client._clients_by_email.clear()
    Client.counter = 0
    PortfolioValue.clear_daily_values()
    clear_history_state()

    _clear_orderbook_state_table()


@pytest.fixture
def database_snapshot(test_db_path: Path):
    """Per-test database snapshot/cleanup helper for DB-facing tests."""
    db_path = test_db_path

    with tempfile.TemporaryDirectory() as tmpdir:
        backup = Path(tmpdir) / db_path.name
        shutil.copy2(db_path, backup)
        try:
            yield
        finally:
            _restore_database_from_backup(db_path, backup)


@pytest.fixture
def app_module(reset_domain_state):
    """Import a fresh app module so state built at module import is deterministic."""
    OrderBook._all_books.clear()
    OrderBook._tickers.clear()
    OrderBook.counter = 0

    Order._all_orders.clear()
    Order.counter = 0

    Client._all_clients.clear()
    Client._clients_by_username.clear()
    Client._clients_by_email.clear()
    Client.counter = 0
    PortfolioValue.clear_daily_values()
    clear_history_state()

    return reload(import_module("app.main"))


@pytest.fixture
def api_client(app_module):
    with TestClient(
        app_module.app,
        headers={
            "X-Actor-User": "tapple",
            "X-Actor-Email": "timcook@aol.com",
        },
    ) as client:
        yield client


@pytest.fixture
def default_ticker():
    return "AAPL"


def pytest_collection_modifyitems(items):
    for item in items:
        path = str(item.fspath)
        if "/tests/api/" in path:
            item.add_marker(pytest.mark.api)
        elif "/tests/integration/" in path:
            item.add_marker(pytest.mark.integration)
        elif "/tests/unit/" in path:
            item.add_marker(pytest.mark.unit)
