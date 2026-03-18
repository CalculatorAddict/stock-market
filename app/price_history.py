from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone

from engine.order_book import OrderBook
from models.client import Client
from market_constants import OPENING_PRICES, TICKERS


DEFAULT_WINDOW_SECONDS = 60
_price_history = {ticker: deque() for ticker in TICKERS}
_last_sample_price = {ticker: OPENING_PRICES[ticker] for ticker in TICKERS}
_last_trade_timestamp_ms = {ticker: None for ticker in TICKERS}
_portfolio_value_history: dict[str, deque] = {}
_last_sample_portfolio_value: dict[str, float] = {}


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


def _resolve_portfolio_mark_price(ticker: str) -> float:
    best_bid = OrderBook.get_best_bid(ticker)
    best_ask = OrderBook.get_best_ask(ticker)
    if best_bid is not None and best_ask is not None and best_bid > 0 and best_ask > 0:
        return float((best_bid + best_ask) / 2)

    last_price = OrderBook.get_last_price(ticker)
    if last_price is not None:
        return float(last_price)

    return float(_last_sample_price[ticker])


def _client_history_key(client: Client) -> str:
    return client.email.strip().lower()


def _compute_portfolio_value(client: Client) -> float:
    holdings_value = 0.0
    for ticker, volume in client.portfolio.items():
        holdings_value += _resolve_portfolio_mark_price(ticker) * volume
    return float(client.balance + holdings_value)


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


def sample_portfolio_values(now: datetime | None = None) -> None:
    sample_time = now or datetime.now(timezone.utc)
    cutoff = sample_time - timedelta(seconds=DEFAULT_WINDOW_SECONDS)

    for client in Client._all_clients.values():
        history_key = _client_history_key(client)
        next_value = _compute_portfolio_value(client)
        history = _portfolio_value_history.setdefault(history_key, deque())

        if not history:
            history.append(
                {
                    "date": cutoff,
                    "value": next_value,
                }
            )

        history.append(
            {
                "date": sample_time,
                "value": next_value,
            }
        )
        _last_sample_portfolio_value[history_key] = next_value

        while history and history[0]["date"] < cutoff:
            history.popleft()


def get_price_history(ticker: str, window_seconds: int = DEFAULT_WINDOW_SECONDS):
    if window_seconds <= 0:
        raise ValueError("Window must be a positive integer.")

    if not _price_history[ticker]:
        sample_prices()

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)
    points = [
        {
            "date": point["date"],
            "price": point["price"],
        }
        for point in _price_history[ticker]
        if point["date"] >= cutoff
    ]

    if points:
        if points[0]["date"] > cutoff:
            points.insert(
                0,
                {
                    "date": cutoff,
                    "price": points[0]["price"],
                },
            )
        return points

    fallback_price = float(_last_sample_price[ticker])
    return [
        {"date": cutoff, "price": fallback_price},
        {"date": now, "price": fallback_price},
    ]


def get_portfolio_value_history(
    client: Client, window_seconds: int = DEFAULT_WINDOW_SECONDS
):
    if window_seconds <= 0:
        raise ValueError("Window must be a positive integer.")

    history_key = _client_history_key(client)
    if history_key not in _portfolio_value_history:
        sample_portfolio_values()

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)
    points = [
        {
            "date": point["date"],
            "value": point["value"],
        }
        for point in _portfolio_value_history.get(history_key, [])
        if point["date"] >= cutoff
    ]

    if points:
        if points[0]["date"] > cutoff:
            points.insert(
                0,
                {
                    "date": cutoff,
                    "value": points[0]["value"],
                },
            )
        return points

    fallback_value = _last_sample_portfolio_value.get(history_key)
    if fallback_value is None:
        fallback_value = _compute_portfolio_value(client)

    return [
        {"date": cutoff, "value": float(fallback_value)},
        {"date": now, "value": float(fallback_value)},
    ]


def clear_history_state() -> None:
    _price_history.clear()
    _price_history.update({ticker: deque() for ticker in TICKERS})
    _last_sample_price.clear()
    _last_sample_price.update({ticker: OPENING_PRICES[ticker] for ticker in TICKERS})
    _last_trade_timestamp_ms.clear()
    _last_trade_timestamp_ms.update({ticker: None for ticker in TICKERS})
    _portfolio_value_history.clear()
    _last_sample_portfolio_value.clear()
