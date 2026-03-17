from __future__ import annotations

from datetime import datetime, timezone
from typing import Self

from models.client import Client
from models.enums import LIMIT, MARKET, BuyOrSell


class Order:
    counter = 0
    _all_orders: list[Self] = []

    def __init__(
        self,
        stock_id: int,
        ticker: str,
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
        self.ticker = ticker
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
        return f"Order[{self.order_id}]: {(self.side, self.ticker, self.volume)} @ {self.price}"

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

    def get_client(self) -> Client:
        return self.client

    def get_stock_id(self) -> int:
        return self.stock_id

    def get_executed_volume(self) -> int:
        return self._total_volume - self.volume

    def get_ticker(self) -> str:
        return self.ticker

    def terminate(self) -> str:
        """Terminate an order and return a log after the termination."""
        self.terminated = True

        # log termination
        return f"Order[{self.order_id}] terminated after {self.get_executed_volume()}/{self._total_volume} shares executed"
