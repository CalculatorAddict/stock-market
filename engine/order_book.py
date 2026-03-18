from __future__ import annotations

from datetime import datetime, timezone
from typing import Self

from sortedcontainers import SortedList

from market_constants import OPENING_PRICES
from models.enums import BUY, SELL, LIMIT, BuyOrSell
from models.order import Order
from models.transaction import Transaction


class OrderBook:
    counter = 0
    _all_books: dict[int, Self] = {}
    _tickers: dict[str, Self] = {}

    def __init__(self, ticker: str):
        self.stock_id: int = OrderBook.counter
        OrderBook.counter += 1
        OrderBook._all_books[self.stock_id] = self
        if not ticker:
            ticker = str(self.stock_id)
        self.ticker = ticker
        OrderBook._tickers[ticker] = self
        self.bids = SortedList(key=lambda o: (-o.price, o.timestamp))
        self.asks = SortedList(key=lambda o: (o.price, o.timestamp))
        self._opening_price = OPENING_PRICES[ticker] if ticker in OPENING_PRICES else 50
        self.last_price = Transaction.last_price_before(
            ticker
        )  # the last price of a transaction
        self.last_timestamp = datetime.now(
            timezone.utc
        )  # last date and time when a transaction has been made

    def get_ticker(self) -> str:
        return self.ticker

    def get_opening_price(self) -> float:
        return self._opening_price

    @classmethod
    def get_all_books(cls) -> dict:
        """Returns all order books as a dict { stock_id -> ticker }"""
        return {book_id: book.ticker for book_id, book in cls._all_books.items()}

    @classmethod
    def get_book_by_id(cls, id: int) -> Self:
        return cls._all_books.get(id)

    @classmethod
    def get_ticker_by_id(cls, id: int) -> str:
        book = cls.get_book_by_id(id)
        if not book:
            return None
        return book.ticker

    @classmethod
    def get_book_by_ticker(cls, ticker: str) -> Self:
        if ticker not in cls._tickers:
            raise KeyError(f"Ticker {ticker} not found")

        return cls._tickers[ticker]

    # object as parameter, NOT IDs
    def _add_order(self, order: Order):
        """Add a limit order to the local side of the book."""
        if order.type is not LIMIT:
            raise ValueError("Only limit orders can be added to limit order book.")

        same_book = self.bids if order.side == BUY else self.asks
        if order.volume > 0 and not order.terminated:
            same_book.add(order)

    # object as parameter, NOT IDs
    def _remove_order(self, order: Order, cancelling=False) -> str:
        """Remove order from local side of the book and optionally terminate it."""
        book = self.bids if order.side == BUY else self.asks
        if order in book:
            book.remove(order)

        if cancelling:
            return order.terminate()
        return "Order removed from book"

    def _get_best_bid(self) -> float | None:
        """Returns highest bid price."""
        return self.bids[0].get_price() if self.bids else None

    def _get_best_ask(self) -> float | None:
        """Returns lowest ask price."""
        return self.asks[0].get_price() if self.asks else None

    def _get_best(self) -> tuple[float | None, float | None]:
        """Returns tuple with (highest bid, lowest ask)."""
        return (self._get_best_bid(), self._get_best_ask())

    @staticmethod
    def get_best_bid(ticker: str) -> float | None:
        stock = OrderBook.get_book_by_ticker(ticker)
        return stock._get_best_bid()

    @staticmethod
    def get_best_ask(ticker: str) -> float | None:
        stock = OrderBook.get_book_by_ticker(ticker)
        return stock._get_best_ask()

    @staticmethod
    def get_best(ticker: str) -> tuple[float | None, float | None]:
        stock = OrderBook.get_book_by_ticker(ticker)
        return stock._get_best()

    def _get_volume_at_price(self, side: BuyOrSell, price: float) -> int:
        """Returns volume of open orders (some of which may not be executable) for given side of the order book."""
        book = self.bids if side == BUY else self.asks

        index = 0
        volume = 0

        while index < len(book) and book[index].get_price() != price:
            index += 1

        while index < len(book) and book[index].get_price() == price:
            volume += book[index].get_volume()
            index += 1

        return volume

    @staticmethod
    def get_volume_at_price(ticker: str, side: BuyOrSell, price: float) -> int:
        stock = OrderBook.get_book_by_ticker(ticker)
        return stock._get_volume_at_price(side, price)

    def _get_all_asks(self) -> list[tuple[int, datetime, float, int, int]]:
        """Returns all asks as a list of 5-tuples (order_id, timestamp, price, volume, stock_id)."""
        return [
            (o.order_id, o.timestamp, o.price, o.volume, o.stock_id) for o in self.asks
        ]

    def _get_all_bids(self) -> list[tuple[int, datetime, float, int, int]]:
        """Returns all bids as a list of 5-tuples (order_id, timestamp, price, volume, stock_id)."""
        return [
            (o.order_id, o.timestamp, o.price, o.volume, o.stock_id) for o in self.bids
        ]

    @staticmethod
    def get_all_asks(ticker: str) -> list[tuple[int, datetime, float, int, int]]:
        """Returns all asks of the stock identified by ticker."""
        stock = OrderBook.get_book_by_ticker(ticker)

        return stock._get_all_asks()

    @staticmethod
    def get_all_bids(ticker: str) -> list[tuple[int, datetime, float, int, int]]:
        """Returns all bids of the stock identified by ticker."""
        stock = OrderBook.get_book_by_ticker(ticker)

        return stock._get_all_bids()

    def _get_last_price(self) -> float:
        return self.last_price

    @staticmethod
    def get_last_price(ticker: str) -> float:
        """Returns the last price of the stock identified by ticker."""
        stock = OrderBook.get_book_by_ticker(ticker)

        return stock._get_last_price()

    def _get_last_timestamp(self) -> datetime:
        return self.last_timestamp

    @staticmethod
    def get_last_timestamp(ticker: str) -> datetime:
        """Returns the last price of the stock identified by ticker."""
        stock = OrderBook.get_book_by_ticker(ticker)

        return stock._get_last_timestamp()

    @staticmethod
    def update_all_last_times(date: datetime):
        for book in OrderBook._all_books.values():
            book.last_timestamp = date
