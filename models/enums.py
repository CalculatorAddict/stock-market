from enum import Enum


class BuyOrSell(Enum):
    BUY = "buy"
    SELL = "sell"

    def opposite(self):
        if self == BUY:
            return SELL
        else:
            return BUY


BUY = BuyOrSell.BUY
SELL = BuyOrSell.SELL


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"


MARKET = OrderType.MARKET
LIMIT = OrderType.LIMIT
