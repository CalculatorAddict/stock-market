from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Self

from sortedcontainers import SortedList

from OrderBook.tickers import OPENING_PRICES
from models.client import Client, ClientInfo
from models.enums import BUY, SELL, BuyOrSell, LIMIT, MARKET
from models.order import Order
from models.transaction import Transaction


class OrderBook:
    counter = 0
    _all_books: list[Self] = []
    _tickers: dict[str, Self] = {}

    def __init__(self, ticker: str):
        self.stock_id: int = OrderBook.counter
        OrderBook.counter += 1
        OrderBook._all_books += [self]
        if not ticker:
            ticker = "" + self.stock_id
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
        return {id: cls._all_books[id].ticker for id in range(len(cls._all_books))}

    @classmethod
    def get_book_by_id(cls, id: int) -> Self:
        try:
            return cls._all_books[id]
        except:
            return None

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

    def _execute_trades_between(
        self, order: Order, opposite_book: SortedList, order_in_book: bool = False
    ):
        """Backward-compatible wrapper around MatchingEngine internals."""
        from engine.matching_engine import MatchingEngine

        MatchingEngine._execute_trades_between(
            self, order, opposite_book, order_in_book=order_in_book
        )

    def _find_matching_order(
        self, order: Order, opposite_book: SortedList
    ) -> Order | None:
        """Backward-compatible wrapper around MatchingEngine internals."""
        from engine.matching_engine import MatchingEngine

        return MatchingEngine._find_matching_order(self, order, opposite_book)

    def match_orders(self):
        """Match all executable resting orders in this book."""
        from engine.matching_engine import MatchingEngine

        MatchingEngine.match(self)

    @staticmethod
    def match_orders_by_ticker(ticker: str = None):
        """Match all executable orders for a given ticker, or all tickers if None."""
        from engine.matching_engine import MatchingEngine

        MatchingEngine.match_by_ticker(ticker)

    # object as parameter, NOT IDs
    def _add_order(self, order: Order):
        """Add a limit order to the order book without attempting to match."""
        if order.type is not LIMIT:
            raise ValueError("Only limit orders can be added to limit order book.")

        same_book = self.bids if order.side == BUY else self.asks

        if order.volume > 0 and not order.terminated:
            same_book.add(order)

    def _market_order(self, order: Order):
        """Execute a market order via MatchingEngine."""
        if order.type is not MARKET:
            raise ValueError("Non-market order cannot be executed as a market order")

        from engine.matching_engine import MatchingEngine

        MatchingEngine.process_order(self, order)
        return order.terminate()

    # object as parameter, NOT IDs
    def _remove_order(self, order: Order, cancelling=False) -> str:
        """Remove an order from the order book."""

        # remove stock from relevant order book
        book = self.bids if order.side == BUY else self.asks

        """if not order in book:
            raise ValueError("Order must be in book to be removed")

            What if I try to remove an order that is not in the book?
            When I cancel an order before putting it in the book.
        """

        if order in book:
            book.remove(order)

        if cancelling:
            return order.terminate()  # mark order as cancelled
        return "Order removed from book"  # if not cancelling

    def _place_order(
        self,
        side: BuyOrSell,
        price: float,
        volume: int,
        client: Client,
        is_market: bool,
    ) -> int:
        """Place order directly with the information entered."""
        print(
            "client info in _place_order",
            client.balance,
            client.client_id,
            client.email,
            client.first_names,
            client.last_name,
            client.portfolio,
            client.username,
        )

        order = Order(self.stock_id, side, price, volume, client.client_id, is_market)
        print("order info in _place_order", order.price, order.client, order.price)
        from engine.matching_engine import MatchingEngine

        MatchingEngine.process_order(self, order)
        if not is_market:
            self._add_order(order)
        return order.order_id

    @staticmethod
    def calculate_pnl(ticker: str, timestamp: datetime) -> float:
        """Calculates the percent profit or loss of a stock with given ticker from a given time."""
        """
        !!!! > not supported between instances of datetime.datetime and builtin_function_or_method
        if timestamp > datetime.now:
            raise ValueError("Cannot calculate pnl with respect to a future time.")"""

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
        return OrderBook.calculate_pnl(
            ticker, datetime.now(timezone.utc) + timedelta(hours=-24)
        )

    @staticmethod
    def place_order(
        ticker: str, side: BuyOrSell, price: float, volume: int, client_info: ClientInfo
    ) -> int:
        """Static method to place an order with the ticker."""
        client = Client.resolve(client_info)

        stock = OrderBook.get_book_by_ticker(ticker)
        print(
            "client info in place_order",
            client.balance,
            client.client_id,
            client.email,
            client.first_names,
            client.last_name,
            client.portfolio,
            client.username,
        )

        return stock._place_order(side, price, volume, client, is_market=False)

    @staticmethod
    def market_order(
        ticker: str, side: BuyOrSell, volume: int, client_info: ClientInfo
    ) -> int:
        """Static method to place an order with the ticker."""
        client = Client.resolve(client_info)

        stock = OrderBook.get_book_by_ticker(ticker)
        print(
            "client info in place_order",
            client.balance,
            client.client_id,
            client.email,
            client.first_names,
            client.last_name,
            client.portfolio,
            client.username,
        )

        price = 0  # placeholder price for input to _place_order

        return stock._place_order(side, price, volume, client, is_market=True)

    @staticmethod
    def cancel_order(order_id: int) -> str:
        """Static method to cancel an order with ticker and order id."""

        '''if(order_id > Order.counter):
            return f"Order {order_id} does not exist"'''

        order = Order.get_order_by_id(order_id)
        ticker = order.ticker
        stock = OrderBook.get_book_by_ticker(ticker)

        return stock._remove_order(order, cancelling=True)

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

    # objects as parameter, NOT IDs
    def _edit_order(
        self, order: Order, new_price: float, new_vol: int
    ) -> tuple[int, str]:
        """Edits order with new price and volume. Returns difference in volumes (as it may not be possible to change volume fully)."""

        if order == None:
            return (0, "Order does not exist")

        self._remove_order(
            order, cancelling=False
        )  # and temporarily remove from the order book

        # then update it and add back
        order.set_price(new_price)
        diff = order.set_volume(new_vol)

        from engine.matching_engine import MatchingEngine

        MatchingEngine.process_order(self, order)
        self._add_order(order)
        return (diff, "Order edited")  # is this really desired ? @Crroco
        # I think we can have this, maybe it helps when we try to automate the trading, so we actually know how much the new order actually is)
        # I think the only "ambiguity" here is for the following case:
        # first I have an order for 10 shares and 7 of them go through, so I am left with 3s.
        # and know I want to change the order to 2 shares (2 < 7 shares which I already transactioned). I think we can do 3 things here:
        # 1. Just cancel the whole order (which happens now because diff = -volume => volume ends up being 0 => cancel), but the traded shares are not recovered.
        # 2. Try to do the inverse order with volume =  7 - 2 at the same price, so we "technically" lose no money
        # 3. Don't allow the change and throw an error. (this seems pointless, but I still included it)

    @staticmethod
    def edit_order(order_id: int, new_price: float, new_vol: int) -> tuple[int, str]:
        """Edits order identified by order id."""
        order = Order.get_order_by_id(order_id)
        ticker = order.ticker
        stock = OrderBook.get_book_by_ticker(ticker)

        return stock._edit_order(order, new_price, new_vol)

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
    def portfolio_value(client_info: ClientInfo) -> float:
        """Returns the total value of a given client's portfolio."""
        client = Client.resolve(client_info)

        cash_value = client.get_balance()
        stock_value = 0
        for ticker in client.portfolio:
            # the value from a given stock is price * volume
            price = OrderBook.get_book_by_ticker(ticker).last_price
            volume = client.portfolio[ticker]
            stock_value += price * volume

        return cash_value + stock_value

    @staticmethod
    def portfolio_pnl(client_info: ClientInfo) -> float:
        """Returns the percent pnl of the given client's portfolio, calculated relative to their portfolio value at market open."""
        client = Client.resolve(client_info)

        current_value = OrderBook.portfolio_value(client_info)
        previous_value = client._daily_portfolio_value

        if previous_value == 0:
            raise AssertionError(
                "Previous portfolio value is 0. Please report this error to the maintainer."
            )

        return (current_value - previous_value) / previous_value * 100

    @staticmethod
    def update_all_last_times(date: datetime):
        for book in OrderBook._all_books:
            book.last_timestamp = date
