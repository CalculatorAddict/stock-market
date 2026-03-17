from __future__ import annotations

from datetime import datetime, timezone, timedelta

from models.client import Client, ClientInfo
from models.transaction import Transaction


class PortfolioValue:
    """Portfolio and ticker valuation helpers with daily client baselines."""

    _daily_values: dict[int, float] = {}

    @staticmethod
    def current_value(client_info: ClientInfo) -> float:
        """Returns the current mark-to-market portfolio value for a client."""
        from engine.order_book import OrderBook

        client = Client.resolve(client_info)

        cash_value = client.get_balance()
        stock_value = 0.0
        for ticker, volume in client.portfolio.items():
            price = OrderBook.get_book_by_ticker(ticker).last_price
            stock_value += price * volume

        return cash_value + stock_value

    @classmethod
    def get_daily_value(cls, client_info: ClientInfo) -> float:
        """Returns the stored daily baseline value for a client."""
        client = Client.resolve(client_info)
        if client.client_id not in cls._daily_values:
            cls._daily_values[client.client_id] = cls.current_value(client)
        return cls._daily_values[client.client_id]

    @classmethod
    def update_daily_value(cls, client_info: ClientInfo) -> float:
        """Updates and returns the daily baseline value for a client."""
        client = Client.resolve(client_info)
        value = cls.current_value(client)
        cls._daily_values[client.client_id] = value
        return value

    @classmethod
    def update_all_daily_values(cls) -> None:
        """Refreshes daily baseline values for all clients."""
        for client in Client._all_clients.values():
            cls.update_daily_value(client)

    @classmethod
    def pnl_percent(cls, client_info: ClientInfo) -> float:
        """Returns portfolio PnL percentage relative to the stored daily value."""
        current = cls.current_value(client_info)
        previous = cls.get_daily_value(client_info)

        if previous == 0:
            raise AssertionError(
                "Previous portfolio value is 0. Please report this error to the maintainer."
            )

        return (current - previous) / previous * 100

    @staticmethod
    def calculate_pnl(ticker: str, timestamp: datetime) -> float:
        """Calculates ticker PnL percent from a historical timestamp to now."""
        from engine.order_book import OrderBook

        stock = OrderBook.get_book_by_ticker(ticker)
        old_price = Transaction.last_price_before(stock.ticker, timestamp)
        new_price = stock.last_price

        if old_price == 0:
            raise AssertionError(
                "Previous portfolio value is 0. Please report this error to the maintainer."
            )

        return (new_price - old_price) / old_price * 100

    @staticmethod
    def calculate_pnl_24h(ticker: str) -> float:
        """Calculates ticker PnL percent over the trailing 24 hours."""
        return PortfolioValue.calculate_pnl(
            ticker, datetime.now(timezone.utc) + timedelta(hours=-24)
        )

    @classmethod
    def clear_daily_values(cls) -> None:
        """Clears all stored daily baseline values."""
        cls._daily_values.clear()
