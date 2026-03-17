from __future__ import annotations

from datetime import datetime, timezone
from typing import Self, TYPE_CHECKING

from models.client import Client
from models.enums import BUY, SELL, LIMIT, MARKET, BuyOrSell

if TYPE_CHECKING:
    from engine.order_book import OrderBook


def _orderbook_cls():
    from OrderBook.OrderBook import OrderBook

    return OrderBook


class Order:
    counter = 0
    _all_orders: list[Self] = []

    def __init__(
        self,
        stock_id: int,
        side: BuyOrSell,
        price: float,
        volume: int,
        client_id: int,
        is_market_order: bool = False,
    ):
        self.order_id = Order.counter
        Order.counter += 1
        Order._all_orders += [self]

        self.timestamp = datetime.now(timezone.utc)
        self.stock_id = stock_id
        self.stock: OrderBook = _orderbook_cls().get_book_by_id(stock_id)
        self.ticker: str = self.stock.ticker
        self.side = side
        self.price = price
        self.volume = volume  # this is volume left to trade
        self.client_id = client_id
        self.client: Client = Client.get_client_by_id(client_id)
        self.terminated = False

        self.type = MARKET if is_market_order else LIMIT

        self._total_volume = volume  # constant keeping track of total volume
        self.transaction_ids: list[int] = []

    def __str__(self):
        return f"Order[{self.order_id}]: {self.side,_orderbook_cls().get_ticker_by_id(self.stock_id),self.volume} @ {self.price}"

    @classmethod
    def get_order_by_id(cls, id: int) -> Self:
        try:
            return cls._all_orders[id]
        except:
            return None

    def get_id(self) -> int:
        return self.order_id

    def get_side(self) -> BuyOrSell:
        return self.side

    def get_price(self) -> float:
        return self.price

    def set_price(self, price: float):
        self.price = price

    def get_volume(self) -> int:
        return self.volume

    def get_total_volume(self) -> int:  # to be used in the edit function !!! NOT USED
        return self._total_volume

    def set_volume(
        self, amt: int
    ) -> int:  # to be used in the edit function, this sets the total_volume
        """Sets volume of order and returns the difference in volumes."""
        diff = max(
            amt - self._total_volume, -self.volume
        )  # can't decrease volume by more than itself
        self._total_volume += diff
        self.volume += diff
        return diff

    def execute_trade(
        self,
        transaction_id: int,
        price: float,
        vol: int,
        side: BuyOrSell,
        update_price: bool,
    ):
        """Update state to execute trade."""
        if self.volume < vol:
            raise ValueError(
                "Order volume was exceeded"
            )  # precondition: vol <= self.volume

        self.transaction_ids += [transaction_id]
        self.volume -= vol

        stock = _orderbook_cls().get_book_by_id(self.stock_id)
        if side == BUY:
            self.client.buy_stock(self.stock_id, price, vol)
            if self.volume > 0 and self.client.get_balance() == 0:
                # Keep cancel semantics centralized: cancel by order_id.
                _orderbook_cls().cancel_order(
                    self.order_id
                )  # cancel the order if buyer has run out of funds
        else:  # side == SELL
            self.client.sell_stock(self.stock_id, price, vol)

            ticker = stock.get_ticker()
            if self.volume > 0 and ticker not in self.client.portfolio:
                _orderbook_cls().cancel_order(
                    self.order_id
                )  # cancel the order if seller ran out of stock

        if self.volume == 0:
            self.terminated = True

        if update_price:
            stock.last_price = price
            stock.last_timestamp = datetime.now(timezone.utc)

    def get_client(self) -> Client:
        return self.client

    def get_stock_id(self) -> int:
        return self.stock_id

    def get_stock(self) -> "OrderBook":
        return self.stock

    def get_executed_volume(self) -> int:
        return self._total_volume - self.volume

    def get_ticker(self) -> int:
        return self.ticker

    def terminate(self) -> str:
        """Terminate an order and return a log after the termination."""
        self.terminated = True

        # log termination
        return f"Order[{self.order_id}] terminated after {self.get_executed_volume()}/{self._total_volume} shares executed"

    def is_executable(self) -> bool:
        """Returns whether order is executable at desired price."""
        if self.terminated:  # order isn't executable if terminated
            return False

        if self.type == MARKET:
            return True

        if self.side == SELL:
            ticker = _orderbook_cls().get_ticker_by_id(self.stock_id)
            if ticker in self.client.portfolio:
                return self.client.portfolio[ticker] > 0
            elif not ticker in self.client.portfolio:
                return False
        else:  # self.side == BUY
            return self.client.balance // self.price > 0

    def executable_volume(self, price=None) -> int:
        """
        Returns the maximum possible executable volume of a given order. If 0 is returned,
        then order is cancelled or has no executable volume at the price.

        Precondition: If order is a sell, then ticker is in the seller's portfolio.
        """
        if self.terminated:
            return 0

        price = price if price is not None else self.price

        if self.side == BUY:
            max_feasible_volume = (
                self.client.get_balance() // price
            )  # no fractional shares
        else:  # self.side == SELL
            ticker = _orderbook_cls().get_ticker_by_id(self.stock_id)
            if ticker not in self.client.portfolio:
                return 0
            max_feasible_volume = self.client.portfolio[ticker]

        return min(max_feasible_volume, self.volume)
