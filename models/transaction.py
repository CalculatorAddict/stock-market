from __future__ import annotations

from datetime import datetime, timezone
from typing import Self

from engine.tickers import OPENING_PRICES
from models.enums import BUY, SELL, LIMIT
from models.order import Order
from database import Database


class Transaction:
    _all_transactions: list[Self] = []
    _transaction_offset = -10

    # object as parameter, NOT IDs
    def __init__(self, bid: Order, ask: Order, vol: int, transaction_id: int):
        if bid.get_stock_id() != ask.get_stock_id():
            raise ValueError(
                "Both orders must be from the same stock"
            )  # precondition: bid and ask have same stock
        else:
            stock_id = bid.get_stock_id()
            ticker = bid.get_ticker()

        self.timestamp = datetime.now(timezone.utc)

        # price of market order is set to the price of the counterparty's limit order
        self.bidder = bid.get_client()
        self.bid_price = bid.get_price() if bid.type == LIMIT else ask.get_price()
        self.asker = ask.get_client()
        self.ask_price = ask.get_price() if ask.type == LIMIT else bid.get_price()

        # trade is executed at the price of the order with earlier timestamp
        price = bid.get_price() if bid.timestamp < ask.timestamp else ask.get_price()
        self.price = price
        self.vol = vol
        self.stock_id = stock_id
        self.ticker = ticker

        self.transaction_id = transaction_id
        # If first transaction in the system
        if Transaction._all_transactions == []:
            Transaction._transaction_offset = self.transaction_id
        Transaction._all_transactions += [self]

        # log transaction
        print(self)

    def __str__(self):
        return f"TRANSACTION: {str(self.asker)} sold {str(self.bidder)} {self.vol} shares of {self.ticker} @ {self.price}"

    def get_price(self):
        return self.price

    @classmethod
    def get_transaction_by_id(cls, id: int) -> Self:
        # print(id, Transaction._transaction_offset)
        try:
            return cls._all_transactions[id - Transaction._transaction_offset]
        except:
            return None

    @classmethod
    def get_all_transactions(cls) -> dict[int, tuple[datetime, float, int, int]]:
        """Returns all transactions as a dictionary { transaction_id -> (timestamp, price, volume, stock_id) }."""
        return {
            t.transaction_id: (t.timestamp, t.price, t.vol, t.stock_id)
            for t in cls._all_transactions
        }

    @classmethod
    def get_transactions_of_stock(
        cls, ticker: str
    ) -> list[tuple[int, int, float, int, float, int, str, str, float]]:
        """
        Returns all transactions of a given stock from the database, as a list of tuples.

        Parameters:
        - ticker: The ticker of the order book.

        Returns a list of tuples with entries:
        [0] transaction_id (int)
        [1] bidder_id (int)
        [2] bid_price (float)
        [3] asker_id (int)
        [4] ask_price (float)
        [5] vol (int)
        [6] ticker (str)
        [7] time_stamp (str)
        [8] transaction_price (float)
        """
        return Database().retrieve_transactions_stock(ticker)

    @staticmethod
    def last_price_before(
        ticker: str, timestamp: datetime = datetime.now(timezone.utc)
    ) -> float:
        """Returns the price of the last transaction before a given time."""
        all = Transaction.get_transactions_of_stock(ticker)

        timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")
        timestamp = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f")

        # If there is nothing, just return initial price as the old price
        if len(all) == 0:
            return OPENING_PRICES[ticker]

        max_before = all[0]
        for val in all:
            # print(timestamp, datetime.strptime(val[7], '%Y-%m-%d %H:%M:%S.%f'))
            if (
                datetime.strptime(val[7], "%Y-%m-%d %H:%M:%S.%f") < timestamp
                and val[0] > max_before[0]
            ):
                max_before = val

        if datetime.strptime(max_before[7], "%Y-%m-%d %H:%M:%S.%f") > timestamp:
            return OPENING_PRICES[ticker]

        return max_before[8]
