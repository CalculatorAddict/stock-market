from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from database import Database
from sortedcontainers import SortedList

from models.enums import BuyOrSell, BUY, SELL, LIMIT, MARKET
from models.order import Order
from models.transaction import Transaction

if TYPE_CHECKING:
    from engine.order_book import OrderBook
    from models.client import Client
    from models.order import Order


class MatchingEngine:
    """Single place for matching and execution logic."""

    @staticmethod
    def add_order(order_book: OrderBook, order: Order) -> None:
        """Delegate order insertion to OrderBook state mutator."""
        order_book._add_order(order)

    @staticmethod
    def remove_order(order_book: OrderBook, order: Order, cancelling=False) -> str:
        """Delegate order removal to OrderBook state mutator."""
        return order_book._remove_order(order, cancelling=cancelling)

    @classmethod
    def place_order(
        cls,
        order_book: OrderBook,
        side,
        price: float,
        volume: int,
        client: Client,
        is_market: bool,
    ) -> int:
        order = Order(
            order_book.stock_id,
            order_book.ticker,
            side,
            price,
            volume,
            client.client_id,
            is_market,
        )

        cls.process_order(order_book, order)
        if not is_market:
            cls.add_order(order_book, order)

        return order.order_id

    @classmethod
    def market_order(cls, order_book: OrderBook, order: Order) -> str:
        if order.type is not MARKET:
            raise ValueError("Non-market order cannot be executed as a market order")

        cls.process_order(order_book, order)
        return order.terminate()

    @classmethod
    def edit_order(
        cls, order_book: OrderBook, order: Order | None, new_price: float, new_vol: int
    ) -> tuple[int, str]:
        """Edit order state and re-run matching through the engine."""
        if order is None:
            return (0, "Order does not exist")

        cls.remove_order(order_book, order, cancelling=False)
        order.set_price(new_price)
        diff = order.set_volume(new_vol)

        cls.process_order(order_book, order)
        cls.add_order(order_book, order)
        return (diff, "Order edited")

    @staticmethod
    def _persist_transaction(bid: Order, ask: Order, vol: int, price: float) -> int:
        """Persist a transaction row and return its database id."""
        bidder_db_id = Database().account_from_email(bid.get_client().email)[0]
        asker_db_id = Database().account_from_email(ask.get_client().email)[0]
        bid_price = bid.get_price() if bid.type == LIMIT else ask.get_price()
        ask_price = ask.get_price() if ask.type == LIMIT else bid.get_price()

        return Database().create_transaction(
            bidder_db_id,
            bid_price,
            asker_db_id,
            ask_price,
            vol,
            bid.get_ticker(),
            price,
        )

    @staticmethod
    def _determine_trade_price(bid: Order, ask: Order) -> float:
        """Return execution price using price-time priority."""
        return bid.get_price() if bid.timestamp < ask.timestamp else ask.get_price()

    @classmethod
    def _determine_trade_volume(cls, bid: Order, ask: Order, price: float) -> int:
        """Return executable volume for a bid/ask pair at the execution price."""
        return min(
            cls.executable_volume(bid, price),
            cls.executable_volume(ask, price),
        )

    @staticmethod
    def _validate_trade_execution(order: Order, price: float, vol: int, side) -> None:
        if side not in (BUY, SELL):
            raise ValueError("Invalid trade side")
        if side != order.side:
            raise ValueError("Trade side does not match order side")
        if order.terminated:
            raise ValueError("Terminated order cannot be executed")
        if vol <= 0:
            raise ValueError("Trade volume must be positive")
        if price <= 0:
            raise ValueError("Trade price must be positive")
        if order.volume < vol:
            raise ValueError("Order volume was exceeded")

        if side == BUY:
            if order.client.get_balance() < price * vol:
                raise ValueError(
                    f"Buyer {order.client.username} has insufficient funds"
                )
            return

        available_stock = order.client.portfolio.get(order.ticker, 0)
        if available_stock == 0:
            raise ValueError(f"Seller {order.client.username} does not own the stock")
        if available_stock < vol:
            raise ValueError(f"Seller {order.client.username} has insufficient stock")

    @staticmethod
    def is_executable(order: Order) -> bool:
        if order.terminated:
            return False
        if order.type == MARKET:
            return True
        if order.side == SELL:
            return order.client.portfolio.get(order.ticker, 0) > 0
        return order.client.balance // order.price > 0

    @staticmethod
    def executable_volume(order: Order, price: float | None = None) -> int:
        if order.terminated:
            return 0

        trade_price = order.price if price is None else price
        if order.side == BUY:
            max_feasible_volume = order.client.get_balance() // trade_price
        else:
            max_feasible_volume = order.client.portfolio.get(order.ticker, 0)
        return min(max_feasible_volume, order.volume)

    @classmethod
    def execute_trade(
        cls,
        order_book: OrderBook,
        order: Order,
        transaction_id: int,
        price: float,
        vol: int,
        side: BuyOrSell,
    ) -> None:
        cls._validate_trade_execution(order, price, vol, side)

        order.transaction_ids += [transaction_id]
        order.volume -= vol

        if side == BUY:
            order.client.buy_stock(order.ticker, price, vol)
            if order.volume > 0 and order.client.get_balance() == 0:
                cls.remove_order(order_book, order, cancelling=True)
        else:
            order.client.sell_stock(order.ticker, price, vol)
            if order.volume > 0 and order.ticker not in order.client.portfolio:
                cls.remove_order(order_book, order, cancelling=True)

        if order.volume == 0:
            order.terminated = True

        order_book.last_price = price
        order_book.last_timestamp = datetime.now(timezone.utc)

    @classmethod
    def _execute_trade_pair(
        cls, order_book: OrderBook, bid_order: Order, ask_order: Order
    ) -> bool:
        """Execute a matched bid/ask pair by determining price and volume first."""
        price = cls._determine_trade_price(bid_order, ask_order)
        trade_volume = cls._determine_trade_volume(bid_order, ask_order, price)
        if trade_volume <= 0:
            return False

        transaction_id = cls._persist_transaction(
            bid_order, ask_order, trade_volume, price
        )
        cls.execute_trade(
            order_book, bid_order, transaction_id, price, trade_volume, BUY
        )
        cls.execute_trade(
            order_book, ask_order, transaction_id, price, trade_volume, SELL
        )

        Transaction(bid_order, ask_order, trade_volume, transaction_id)
        return True

    @staticmethod
    def _find_matching_order(
        order_book: OrderBook, order: Order, opposite_book: SortedList
    ) -> Order | None:
        for other_order in list(opposite_book):
            if other_order.client == order.client:
                continue

            if not MatchingEngine.is_executable(other_order):
                MatchingEngine.remove_order(order_book, other_order, cancelling=True)
                continue

            trade_price = other_order.get_price()
            if order.type == LIMIT:
                if order.side != BUY and trade_price < order.get_price():
                    return None
                if order.side == BUY and trade_price > order.get_price():
                    return None

            return other_order

        return None

    @classmethod
    def _execute_trades_between(
        cls,
        order_book: OrderBook,
        order: Order,
        opposite_book: SortedList,
        order_in_book: bool = False,
    ) -> None:
        while cls.is_executable(order) and opposite_book:
            other_order = cls._find_matching_order(order_book, order, opposite_book)
            if other_order is None:
                break

            trade_price = other_order.get_price()
            if order.type == LIMIT:
                if order.side != BUY and trade_price < order.get_price():
                    break
                if order.side == BUY and trade_price > order.get_price():
                    break

            if cls.executable_volume(order, trade_price) == 0:
                break

            if order.side == BUY:
                bid_order, ask_order = order, other_order
            else:
                bid_order, ask_order = other_order, order

            if not cls._execute_trade_pair(order_book, bid_order, ask_order):
                break

            if other_order.get_volume() == 0:
                cls.remove_order(order_book, other_order, cancelling=False)

        if order_in_book and order.terminated:
            cls.remove_order(order_book, order, cancelling=False)

    @classmethod
    def process_order(cls, order_book: OrderBook, order: Order) -> None:
        opposite_book = order_book.asks if order.side == BUY else order_book.bids
        cls._execute_trades_between(order_book, order, opposite_book)

        if order.type == MARKET:
            order.terminate()

    @classmethod
    def match(cls, order_book: OrderBook) -> None:
        orderbook_advanced = True
        while orderbook_advanced:
            orderbook_advanced = False

            while order_book.bids:
                order = order_book.bids[0]
                if order.terminated:
                    continue
                old_volume = order.volume
                cls._execute_trades_between(
                    order_book, order, order_book.asks, order_in_book=True
                )
                if order.volume != old_volume:
                    orderbook_advanced = True
                    break

            if orderbook_advanced:
                continue

            for order in list(order_book.asks):
                if order.terminated:
                    continue
                old_volume = order.volume
                cls._execute_trades_between(
                    order_book, order, order_book.bids, order_in_book=True
                )
                if order.volume != old_volume:
                    orderbook_advanced = True
                    break

    @classmethod
    def match_by_ticker(cls, ticker: str | None = None) -> None:
        from engine.order_book import OrderBook

        if ticker is None:
            for book in OrderBook._all_books.values():
                cls.match(book)
            return

        cls.match(OrderBook.get_book_by_ticker(ticker))
