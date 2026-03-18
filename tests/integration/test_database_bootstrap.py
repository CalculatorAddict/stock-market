import sqlite3

from fastapi.testclient import TestClient

from app.shared_constants import DEMO_CLIENTS
from database import ensure_database_exists

DEFAULT_ACTOR_HEADERS = {
    "X-Actor-User": "tapple",
    "X-Actor-Email": "timcook@aol.com",
}


def _drop_core_tables():
    connection = sqlite3.connect("stock_market_database.db")
    cursor = connection.cursor()
    cursor.executescript(
        """
        DROP TABLE IF EXISTS Transactions;
        DROP TABLE IF EXISTS OwnedStock;
        DROP TABLE IF EXISTS Client;
        """
    )
    connection.commit()
    connection.close()


def test_ensure_database_exists_creates_core_schema(database_snapshot):
    _drop_core_tables()

    result = ensure_database_exists()

    assert result["created_schema"] is True
    assert result["seeded_demo_clients"] is False

    connection = sqlite3.connect("stock_market_database.db")
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name IN ('Client', 'OwnedStock', 'Transactions')
        """
    )
    assert {row[0] for row in cursor.fetchall()} == {
        "Client",
        "OwnedStock",
        "Transactions",
    }
    connection.close()


def test_app_startup_seeds_demo_clients_on_empty_database(
    app_module, database_snapshot
):
    _drop_core_tables()

    with TestClient(app_module.app, headers=DEFAULT_ACTOR_HEADERS):
        connection = sqlite3.connect("stock_market_database.db")
        cursor = connection.cursor()
        cursor.execute("SELECT username, email, balance FROM Client ORDER BY username")
        rows = cursor.fetchall()
        connection.close()

    assert len(rows) == len(DEMO_CLIENTS)

    by_username = {username: (email, balance) for username, email, balance in rows}
    for demo_client in DEMO_CLIENTS:
        assert demo_client["username"] in by_username
        email, balance = by_username[demo_client["username"]]
        assert email == demo_client["email"]
        assert balance == demo_client["balance"]
