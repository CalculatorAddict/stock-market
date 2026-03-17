"""Compatibility facade for refactored order book domain.

Implementation now lives in:
- engine.order_book (OrderBook)
- models.client (Client)
- models.order (Order)
- models.transaction (Transaction)
- models.enums (BUY/SELL, MARKET/LIMIT, enum types)
"""

from engine.order_book import OrderBook
from models.client import Client, ClientInfo
from models.enums import BUY, SELL, BuyOrSell, LIMIT, MARKET, OrderType
from models.order import Order
from models.transaction import Transaction

__all__ = [
    "BuyOrSell",
    "BUY",
    "SELL",
    "OrderType",
    "MARKET",
    "LIMIT",
    "Client",
    "ClientInfo",
    "Order",
    "Transaction",
    "OrderBook",
]
