from OrderBook.OrderBook import BUY, SELL, Client, OrderBook


def _init_context():
    book = OrderBook("AAPL")

    client = Client("maker", "pw", "maker@example.com", "Maker", "User")
    client.portfolio["AAPL"] = 20

    return book, client


def test_edit_order_returns_tuple_delta_for_non_existing_order():
    book, _ = _init_context()
    delta, message = book._edit_order(None, 42.0, 10)

    assert delta == 0
    assert message == "Order does not exist"


def test_cancel_order_keeps_book_clean_after_termination():
    book, client = _init_context()
    order_id = book._place_order(SELL, 105.0, 5, client, is_market=False)

    result = OrderBook.cancel_order(order_id)

    assert result == "Order[%d] terminated after 0/5 shares executed" % order_id
    assert OrderBook.get_all_asks("AAPL") == []


def test_edit_order_updates_price_and_volume():
    book, client = _init_context()
    order_id = book._place_order(SELL, 108.0, 4, client, is_market=False)

    diff, message = OrderBook.edit_order(order_id, 110.0, 7)

    assert message == "Order edited"
    assert diff == 3
    edited_order = book.get_all_asks("AAPL")[0]
    assert edited_order[2] == 110.0
    assert edited_order[3] == 7
