from engine.matching_engine import MatchingEngine
from engine.order_book import OrderBook
from models.client import Client
from models.enums import SELL
from models.order import Order


def _init_context():
    book = OrderBook("OGC")

    client = Client("maker", "pw", "maker@example.com", "Maker", "User")
    client.portfolio["OGC"] = 20

    return book, client


def test_edit_order_returns_tuple_delta_for_non_existing_order():
    book, _ = _init_context()
    delta, message = MatchingEngine.edit_order(book, None, 42.0, 10)

    assert delta == 0
    assert message == "Order does not exist"


def test_cancel_order_keeps_book_clean_after_termination():
    book, client = _init_context()
    order_id = MatchingEngine.place_order(book, SELL, 105.0, 5, client, is_market=False)
    order = Order.get_order_by_id(order_id)

    result = MatchingEngine.remove_order(book, order, cancelling=True)

    assert result == "Order[%d] terminated after 0/5 shares executed" % order_id
    assert OrderBook.get_all_asks("OGC") == []


def test_edit_order_updates_price_and_volume():
    book, client = _init_context()
    order_id = MatchingEngine.place_order(book, SELL, 108.0, 4, client, is_market=False)
    order = Order.get_order_by_id(order_id)

    diff, message = MatchingEngine.edit_order(book, order, 110.0, 7)

    assert message == "Order edited"
    assert diff == 3
    edited_order = book.get_all_asks("OGC")[0]
    assert edited_order[2] == 110.0
    assert edited_order[3] == 7
