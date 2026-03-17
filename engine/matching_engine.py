from __future__ import annotations

from typing import TYPE_CHECKING

from sortedcontainers import SortedList

if TYPE_CHECKING:
    from OrderBook.OrderBook import Order, OrderBook


class MatchingEngine:
    """Single place for order matching and transaction execution."""

    @staticmethod
    def _find_matching_order(
        order_book: "OrderBook", order: "Order", opposite_book: SortedList
    ) -> "Order | None":
        from OrderBook.OrderBook import BUY, LIMIT

        for other_order in list(opposite_book):
            if other_order.client == order.client:
                continue

            if not other_order.is_executable():
                order_book._remove_order(other_order, cancelling=True)
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
        order_book: "OrderBook",
        order: "Order",
        opposite_book: SortedList,
        order_in_book: bool = False,
    ) -> None:
        from OrderBook.OrderBook import BUY, LIMIT, Transaction

        while order.is_executable() and opposite_book:
            other_order = cls._find_matching_order(order_book, order, opposite_book)
            if other_order is None:
                break

            trade_price = other_order.get_price()

            if order.type == LIMIT:
                if order.side != BUY and trade_price < order.get_price():
                    break
                if order.side == BUY and trade_price > order.get_price():
                    break

            if order.executable_volume(trade_price) == 0:
                break

            trade_volume = min(
                order.executable_volume(trade_price),
                other_order.executable_volume(trade_price),
            )
            if trade_volume <= 0:
                break

            if order.side == BUY:
                Transaction(order, other_order, trade_volume)
            else:
                Transaction(other_order, order, trade_volume)

            if other_order.get_volume() == 0:
                order_book._remove_order(other_order, cancelling=False)

        if order_in_book and order.terminated:
            order_book._remove_order(order, cancelling=False)

    @classmethod
    def process_order(cls, order_book: "OrderBook", order: "Order") -> None:
        from OrderBook.OrderBook import BUY, MARKET

        opposite_book = order_book.asks if order.side == BUY else order_book.bids
        cls._execute_trades_between(order_book, order, opposite_book)

        if order.type == MARKET:
            order.terminate()

    @classmethod
    def match(cls, order_book: "OrderBook") -> None:
        """
        Match all executable resting orders in this book until no additional
        matches can be made without new orderbook input.
        """
        orderbook_advanced = True
        while orderbook_advanced:
            orderbook_advanced = False

            for order in list(order_book.bids):
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
        from OrderBook.OrderBook import OrderBook

        if ticker is None:
            for book in OrderBook._all_books:
                cls.match(book)
            return

        cls.match(OrderBook.get_book_by_ticker(ticker))
