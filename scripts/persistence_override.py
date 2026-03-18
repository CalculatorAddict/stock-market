#!/usr/bin/env python3
import sqlite3
from pathlib import Path

ORDERBOOK_STATE_TABLE = "orderbook_state"
DATABASE_PATH = Path(__file__).resolve().parent.parent / "stock_market_database.db"


def drop_orderbook_state_table(database_path: Path = DATABASE_PATH) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"DROP TABLE IF EXISTS {ORDERBOOK_STATE_TABLE}")
        connection.commit()


def main() -> None:
    drop_orderbook_state_table()
    print(f"Dropped {ORDERBOOK_STATE_TABLE} from {DATABASE_PATH}")


if __name__ == "__main__":
    main()
