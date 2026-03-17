from importlib import import_module, reload
from pathlib import Path
import os
import shutil
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(os.path.dirname(os.path.abspath(__file__))).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from OrderBook.OrderBook import Client, Order, OrderBook


def _restore_database_from_backup(db_path: Path, backup: Path) -> None:
    shutil.copy2(backup, db_path)


@pytest.fixture(autouse=True)
def reset_domain_state():
    """Reset shared domain state before each test for isolation."""
    OrderBook._all_books.clear()
    OrderBook._tickers.clear()
    OrderBook.counter = 0

    Order._all_orders.clear()
    Order.counter = 0

    Client._all_clients.clear()
    Client._usernames.clear()
    Client.counter = 0


@pytest.fixture
def database_snapshot():
    """Per-test database snapshot/cleanup helper for DB-facing tests."""
    db_path = ROOT_DIR / "stock_market_database.db"

    if not db_path.exists():
        yield
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        backup = Path(tmpdir) / db_path.name
        shutil.copy2(db_path, backup)
        try:
            yield
        finally:
            _restore_database_from_backup(db_path, backup)


@pytest.fixture
def app_module():
    """Import a fresh app module so state built at module import is deterministic."""
    OrderBook._all_books.clear()
    OrderBook._tickers.clear()
    OrderBook.counter = 0

    Order._all_orders.clear()
    Order.counter = 0

    Client._all_clients.clear()
    Client._usernames.clear()
    Client.counter = 0

    return reload(import_module("app.main"))


@pytest.fixture
def api_client(app_module):
    with TestClient(app_module.app) as client:
        yield client


@pytest.fixture
def default_ticker():
    return "AAPL"
