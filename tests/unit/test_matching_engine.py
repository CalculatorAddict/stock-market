from OrderBook.OrderBook import BUY as BUY_SIDE, SELL as SELL_SIDE
from OrderBook.OrderBook import Client, Order, OrderBook


def _build_book_with_clients(ticker="AAPL"):
    book = OrderBook(ticker)

    buyer = Client("buyer", "pw", "buyer@example.com", "Buy", "Er", balance=100_000)
    seller = Client("seller", "pw", "seller@example.com", "Sell", "Er", balance=0)
    seller.portfolio[ticker] = 10

    return book, buyer, seller


def test_empty_book_best_is_zero():
    book, _, _ = _build_book_with_clients()

    assert book._get_best() == (0, 0)
    assert OrderBook.get_best("AAPL") == (0, 0)


def test_matching_engine_keeps_multiple_orders_at_same_price_aggregated():
    book, buyer1, buyer2 = _build_book_with_clients()

    book._place_order(BUY_SIDE, 100.0, 2, buyer1, is_market=False)
    book._place_order(BUY_SIDE, 100.0, 3, buyer2, is_market=False)

    assert OrderBook.get_volume_at_price("AAPL", BUY_SIDE, 100.0) == 5


def test_orderbook_get_best_bid_prefers_highest_price_level():
    book, buyer1, buyer2 = _build_book_with_clients()

    book._place_order(BUY_SIDE, 100.0, 1, buyer1, is_market=False)
    book._place_order(BUY_SIDE, 102.5, 2, buyer2, is_market=False)

    assert OrderBook.get_best_bid("AAPL") == 102.5


class _NoDbTransaction:
    """Execute the same trade side effects without writing to the database."""

    def __init__(self, bid, ask, vol):
        self.price = (
            bid.get_price() if bid.timestamp < ask.timestamp else ask.get_price()
        )
        bid.execute_trade(1, self.price, vol, BUY_SIDE, True)
        ask.execute_trade(2, self.price, vol, SELL_SIDE, True)


def test_partial_fill_updates_remaining_order_volume(monkeypatch):
    book, buyer, seller = _build_book_with_clients()
    monkeypatch.setattr("OrderBook.OrderBook.Transaction", _NoDbTransaction)

    sell_id = book._place_order(SELL_SIDE, 101.0, 10, seller, is_market=False)
    buy_id = book._place_order(BUY_SIDE, 102.0, 4, buyer, is_market=False)

    ask_order = Order.get_order_by_id(sell_id)
    bid_order = Order.get_order_by_id(buy_id)

    assert ask_order.get_volume() == 6
    assert bid_order.volume == 0
    assert OrderBook.get_best("AAPL") == (0, 101.0)
    assert book.last_price == 101.0
    assert ask_order.terminated is False


def test_unfeasible_first_bid_order_is_cancelled_when_counter_order_arrives():
    book = OrderBook("AAPL")

    buy_only_client = Client("poor_buyer", "pw", "poor@example.com", "Poor", "Buyer", 0)
    sell_client = Client("seller", "pw", "seller@example.com", "Seller", "Able", 0)
    sell_client.portfolio["AAPL"] = 5

    bid_id = book._place_order(BUY_SIDE, 100.0, 5, buy_only_client, is_market=False)
    ask_id = book._place_order(SELL_SIDE, 100.0, 5, sell_client, is_market=False)

    assert OrderBook.get_all_bids("AAPL") == []
    assert len(OrderBook.get_all_asks("AAPL")) == 1

    bid_order = Order.get_order_by_id(bid_id)
    ask_order = Order.get_order_by_id(ask_id)
    assert bid_order.terminated
    assert not ask_order.terminated


def test_unfeasible_first_ask_order_is_cancelled_when_counter_order_arrives():
    book = OrderBook("AAPL")

    buy_client = Client("rich_buyer", "pw", "rich@example.com", "Rich", "Buyer", 10_000)
    no_stock_client = Client(
        "poor_seller", "pw", "poor@example.com", "Poor", "Seller", 0
    )

    ask_id = book._place_order(SELL_SIDE, 100.0, 5, no_stock_client, is_market=False)
    bid_id = book._place_order(BUY_SIDE, 100.0, 5, buy_client, is_market=False)

    assert OrderBook.get_all_asks("AAPL") == []
    assert len(OrderBook.get_all_bids("AAPL")) == 1

    ask_order = Order.get_order_by_id(ask_id)
    bid_order = Order.get_order_by_id(bid_id)
    assert ask_order.terminated
    assert not bid_order.terminated


def test_unfeasible_counter_order_is_retained_when_first_side_is_executable():
    book = OrderBook("AAPL")

    seller = Client(
        "seller", "pw", "seller@example.com", "Seller", "Able", 0, {"AAPL": 10}
    )
    poor_buyer = Client("poor_buyer", "pw", "poor@example.com", "Poor", "Buyer", 0)

    ask_id = book._place_order(SELL_SIDE, 100.0, 5, seller, is_market=False)
    bid_id = book._place_order(BUY_SIDE, 100.0, 5, poor_buyer, is_market=False)

    assert len(OrderBook.get_all_asks("AAPL")) == 1
    assert len(OrderBook.get_all_bids("AAPL")) == 1

    ask_order = Order.get_order_by_id(ask_id)
    bid_order = Order.get_order_by_id(bid_id)
    assert not ask_order.terminated
    assert not bid_order.terminated


def test_note_3_self_matching_orders_are_not_executed():
    book = OrderBook("AAPL")

    trader = Client("self_trader", "pw", "self@example.com", "Self", "Trader")
    trader.balance = 100_000
    trader.portfolio["AAPL"] = 10

    bid_id = book._place_order(BUY_SIDE, 100.0, 5, trader, is_market=False)
    ask_id = book._place_order(SELL_SIDE, 100.0, 5, trader, is_market=False)

    assert len(OrderBook.get_all_bids("AAPL")) == 1
    assert len(OrderBook.get_all_asks("AAPL")) == 1

    buy_order = Order.get_order_by_id(bid_id)
    sell_order = Order.get_order_by_id(ask_id)
    assert buy_order.volume == 5
    assert sell_order.volume == 5
    assert not buy_order.terminated
    assert not sell_order.terminated


def test_note_13_existing_orders_reconcile_when_matchability_changes():
    book = OrderBook("AAPL")

    buyer = Client("poor_buyer", "pw", "poor@example.com", "Poor", "Buyer", balance=0)
    seller = Client("seller", "pw", "seller@example.com", "Seller", "Able", balance=0)
    seller.portfolio["AAPL"] = 5

    ask_id = book._place_order(SELL_SIDE, 100.0, 3, seller, is_market=False)
    bid_id = book._place_order(BUY_SIDE, 100.0, 3, buyer, is_market=False)

    bid_order = Order.get_order_by_id(bid_id)
    ask_order = Order.get_order_by_id(ask_id)
    assert len(OrderBook.get_all_bids("AAPL")) == 1
    assert len(OrderBook.get_all_asks("AAPL")) == 1
    assert bid_order.volume == 3
    assert ask_order.volume == 3

    buyer.add_funds(1000)

    assert bid_order.volume == 0
    assert ask_order.volume == 0
    assert bid_order.terminated
    assert ask_order.terminated
    assert OrderBook.get_all_bids("AAPL") == []
    assert OrderBook.get_all_asks("AAPL") == []


def test_buyer_partial_fill_then_zero_balance_cancels_remaining_order(monkeypatch):
    book = OrderBook("AAPL")
    monkeypatch.setattr("OrderBook.OrderBook.Transaction", _NoDbTransaction)

    buyer = Client("limited_buyer", "pw", "limited@example.com", "Limited", "Buyer", 10)
    seller = Client("liquid_seller", "pw", "seller@example.com", "Liquid", "Seller", 0)
    seller.portfolio["AAPL"] = 5

    ask_id = book._place_order(SELL_SIDE, 10.0, 5, seller, is_market=False)
    bid_id = book._place_order(BUY_SIDE, 10.0, 2, buyer, is_market=False)

    ask_order = Order.get_order_by_id(ask_id)
    bid_order = Order.get_order_by_id(bid_id)

    assert buyer.balance == 0
    assert buyer.portfolio["AAPL"] == 1
    assert bid_order.terminated is True
    assert bid_order.volume == 1
    assert ask_order.terminated is False
    assert ask_order.volume == 4
    assert OrderBook.get_all_bids("AAPL") == []
