from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone

from engine.order_book import OrderBook
from market_constants import OPENING_PRICES, TICKERS


DEFAULT_WINDOW_SECONDS = 60
_price_history = {ticker: deque() for ticker in TICKERS}
_last_sample_price = {ticker: OPENING_PRICES[ticker] for ticker in TICKERS}
_last_trade_timestamp_ms = {ticker: None for ticker in TICKERS}


def _to_timestamp_ms(raw_value) -> int | None:
    if raw_value is None:
        return None

    if isinstance(raw_value, datetime):
        parsed = raw_value
    else:
        parsed = datetime.fromisoformat(str(raw_value))

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return int(parsed.timestamp() * 1000)


def _resolve_sample_price(ticker: str) -> float:
    best_bid = OrderBook.get_best_bid(ticker)
    best_ask = OrderBook.get_best_ask(ticker)
    last_price = OrderBook.get_last_price(ticker)
    last_timestamp = OrderBook.get_last_timestamp(ticker)

    trade_timestamp_ms = _to_timestamp_ms(last_timestamp)
    if (
        trade_timestamp_ms is not None
        and last_price is not None
        and (
            _last_trade_timestamp_ms[ticker] is None
            or trade_timestamp_ms > _last_trade_timestamp_ms[ticker]
        )
    ):
        _last_trade_timestamp_ms[ticker] = trade_timestamp_ms
        return float(last_price)

    if best_bid is not None and best_ask is not None and best_bid > 0 and best_ask > 0:
        return float((best_bid + best_ask) / 2)

    return float(_last_sample_price[ticker])


def sample_prices(now: datetime | None = None) -> None:
    sample_time = now or datetime.now(timezone.utc)
    cutoff = sample_time - timedelta(seconds=DEFAULT_WINDOW_SECONDS)

    for ticker in TICKERS:
        next_price = _resolve_sample_price(ticker)
        history = _price_history[ticker]

        if not history:
            history.append(
                {
                    "date": cutoff,
                    "price": next_price,
                }
            )

        history.append(
            {
                "date": sample_time,
                "price": next_price,
            }
        )
        _last_sample_price[ticker] = next_price

        while history and history[0]["date"] < cutoff:
            history.popleft()


def get_price_history(ticker: str, window_seconds: int = DEFAULT_WINDOW_SECONDS):
    if window_seconds <= 0:
        raise ValueError("Window must be a positive integer.")

    if not _price_history[ticker]:
        sample_prices()

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    return [
        {
            "date": point["date"],
            "price": point["price"],
        }
        for point in _price_history[ticker]
        if point["date"] >= cutoff
    ]
