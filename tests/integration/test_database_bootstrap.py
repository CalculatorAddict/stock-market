import sqlite3

from fastapi.testclient import TestClient

from app.shared_constants import BOT_CLIENTS, DEMO_CLIENTS
from database import ensure_database_exists
from models.client import Client

DEFAULT_ACTOR_HEADERS = {
    "X-Actor-User": "amorgan",
    "X-Actor-Email": "alex.morgan@demo.local",
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

    assert len(rows) == len(DEMO_CLIENTS) + len(BOT_CLIENTS)

    by_username = {username: (email, balance) for username, email, balance in rows}
    for seeded_client in [*DEMO_CLIENTS, *BOT_CLIENTS]:
        assert seeded_client["username"] in by_username
        email, balance = by_username[seeded_client["username"]]
        assert email == seeded_client["email"]
        assert balance == seeded_client["balance"]


def test_app_startup_normalizes_demo_client_identity(app_module):
    demo_client = Client.get_client_by_username("amorgan")
    assert demo_client is not None
    assert demo_client.email == "alex.morgan@demo.local"
