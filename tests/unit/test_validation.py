import pytest
from fastapi import HTTPException

from app.validation import orderbook_error_to_http, validate_side, validate_ticker
from OrderBook.tickers import TICKERS


def test_validate_ticker_accepts_supported_ticker():
    assert validate_ticker(TICKERS[0]) == TICKERS[0]


def test_validate_ticker_rejects_unknown_ticker():
    with pytest.raises(HTTPException) as exc_info:
        validate_ticker("ZZZ")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Ticker 'ZZZ' not found"


def test_validate_side_accepts_buy_and_sell():
    assert validate_side("Buy") == "buy"
    assert validate_side("SELL") == "sell"


def test_validate_side_rejects_invalid_side():
    with pytest.raises(HTTPException) as exc_info:
        validate_side("hold")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid side. Must be either 'buy' or 'sell'."


def test_orderbook_error_to_http_maps_key_error_to_404():
    with pytest.raises(HTTPException) as exc_info:
        try:
            raise KeyError("Order 123 does not exist")
        except KeyError as err:
            orderbook_error_to_http(err)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Order 123 does not exist"


def test_orderbook_error_to_http_maps_generic_error_to_400():
    with pytest.raises(HTTPException) as exc_info:
        orderbook_error_to_http(ValueError("Bad order state"))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Bad order state"
