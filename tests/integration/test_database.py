import sqlite3

import pytest

from database import Database


def _seed_database() -> None:
    connection = sqlite3.connect("stock_market_database.db")
    cursor = connection.cursor()

    cursor.execute("DELETE FROM Transactions;")
    cursor.execute("DELETE FROM OwnedStock;")
    cursor.execute("DELETE FROM Client;")

    cursor.executescript(
        """
        INSERT INTO Client(client_id, username, email, balance, first_names, last_name) VALUES
            (1, 'A', 'a@a.com', 100.0, 'A', 'Alpha'),
            (2, 'B', 'b@b.com', 100.0, 'B', 'Bravo'),
            (3, 'C', 'c@c.com', 100.0, 'C', 'Charlie'),
            (4, 'D', 'd@d.com', 100.0, 'D', 'Delta'),
            (5, 'E', 'e@e.com', 100.0, 'E', 'Echo');

        INSERT INTO OwnedStock(owner_id, ticker, average_price, total_vol) VALUES
            (1, 'A', 2.0, 10),
            (1, 'C', 1.0, 10),
            (2, 'A', 2.0, 10),
            (3, 'C', 1.0, 20),
            (4, 'A', 2.0, 10),
            (4, 'C', 2.0, 10),
            (5, 'C', 3.0, 10);

        INSERT INTO Transactions (bidder_id, bid_price, asker_id, ask_price, vol, ticker, time_stamp, transaction_price) VALUES
            (1, 2.0, 3, 1.0, 5, 'C', '2025-04-29 10:56:15.364292', 2.0),
            (5, 3.0, 1, 1.0, 1, 'C', '2025-04-29 14:46:55.933437', 3.0),
            (4, 1.0, 1, 1.0, 5, 'A', '2025-04-29 11:00:15.364292', 1.0),
            (1, 2.0, 5, 1.0, 5, 'C', '2025-04-29 14:47:55.933437', 2.0);
        """
    )
    connection.commit()
    connection.close()


@pytest.fixture
def seeded_database(database_snapshot):
    _seed_database()


def test_add_transaction_valid_1(seeded_database):
    result = Database().create_transaction(2, 2, 1, 1, 6, "A", 1)
    assert result != -1

    connection = sqlite3.connect("stock_market_database.db")
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM OwnedStock WHERE owner_id = 2 AND ticker = 'A'")
    assert cursor.fetchone() == (2, "A", 1.62, 16)

    cursor.execute(
        "SELECT bidder_id, bid_price, asker_id, ask_price, vol, ticker, transaction_price FROM Transactions WHERE transaction_id = ?",
        (result,),
    )
    assert cursor.fetchone() == (2, 2, 1, 1, 6, "A", 1)

    connection.close()


def test_add_transaction_valid_2(seeded_database):
    connection = sqlite3.connect("stock_market_database.db")
    cursor = connection.cursor()
    cursor.execute(
        "UPDATE OwnedStock SET total_vol = 20, average_price = 2.0 WHERE owner_id = 1 AND ticker = 'A'"
    )
    connection.commit()
    connection.close()

    result = Database().create_transaction(2, 2, 1, 1, 5, "A", 1)
    assert result != -1

    connection = sqlite3.connect("stock_market_database.db")
    cursor = connection.cursor()
    cursor.execute(
        "SELECT total_vol, average_price FROM OwnedStock WHERE owner_id = 2 AND ticker = 'A'"
    )
    assert cursor.fetchone() == (15, 1.67)

    cursor.execute(
        "SELECT bidder_id, bid_price, asker_id, ask_price, vol, ticker, transaction_price FROM Transactions WHERE transaction_id = ?",
        (result,),
    )
    assert cursor.fetchone() == (2, 2, 1, 1, 5, "A", 1)
    connection.close()


def test_create_transaction_invalid_inputs(seeded_database):
    assert Database().create_transaction(2, 2, 100000, 1, 5, "B", 1) == -1
    assert (
        Database().create_transaction(2, 2, 1, 1, 5, "PleaseDoNotUseThisStock", 1) == -1
    )
    assert Database().create_transaction(2000000, 2, 1, 1, 5, "B", 1) == -1


def test_retrieve_specific_stock(seeded_database):
    assert Database().retrieve_specific_stock(1, "C") == 10
    assert Database().retrieve_specific_stock(10000000, "C") == 0
    assert Database().retrieve_specific_stock(3, "Z") == 0


def test_retrieve_balance(seeded_database):
    assert Database().retrieve_balance(3) == 100.0
    assert Database().retrieve_balance(10000000) == 0


def test_username_and_email_helpers(seeded_database):
    assert Database().is_username_taken("A") is True
    assert Database().is_username_taken("PleaseNeverUseThisUsername") is False
    assert Database().is_email_taken("a@a.com") is True
    assert Database().is_email_taken("PleaseNeverUseThisEmail") is False


def test_create_client(seeded_database):
    username = "PleaseNeverUseThisUsername"
    email = "PleaseNeverUseThisEmail"

    client_id = Database().create_client(username, email)
    assert client_id > 0

    connection = sqlite3.connect("stock_market_database.db")
    cursor = connection.cursor()
    cursor.execute(
        "SELECT client_id FROM Client WHERE username = ? AND email = ?;",
        (username, email),
    )
    assert client_id == cursor.fetchone()[0]

    cursor.execute("DELETE FROM Client WHERE client_id = ?;", (client_id,))
    connection.commit()
    connection.close()


def test_retrieve_stock(seeded_database):
    stock = Database().retrieve_stock(1)
    assert sorted(stock) == sorted([("A", 2.0, 10), ("C", 1.0, 10)])
    assert Database().retrieve_stock(2) == [("A", 2.0, 10)]
    assert Database().retrieve_stock(10000000000) == []


def test_retrieve_transactions(seeded_database):
    assert len(Database().retrieve_transactions_stock("C")) == 3
    assert Database().retrieve_transactions_stock("PleaseNeverUseThisTicker") == []
    assert len(Database().retrieve_transactions_user(1)) > 0
    assert len(Database().retrieve_transactions_user(10000000000)) == 0


def test_create_owned_stock(seeded_database):
    result = Database().create_owned_stock(1, "B", 10)
    assert result is True

    connection = sqlite3.connect("stock_market_database.db")
    cursor = connection.cursor()
    cursor.execute(
        "SELECT * FROM ownedStock WHERE owner_id = 1 AND ticker = 'B' AND total_vol = 10;"
    )
    assert len(cursor.fetchall()) == 1
    connection.close()
