import json
from pathlib import Path


def _load_market_constants() -> tuple[list[str], dict[str, float]]:
    constants_path = (
        Path(__file__).resolve().parent / "static" / "config" / "shared_constants.json"
    )
    with constants_path.open("r", encoding="utf-8") as file_handle:
        payload = json.load(file_handle)

    backend = payload.get("backend", {})
    tickers = [str(ticker) for ticker in backend.get("tickers", [])]
    opening_prices = {
        str(ticker): float(price)
        for ticker, price in backend.get("opening_prices", {}).items()
    }

    if not tickers:
        raise RuntimeError("Missing backend.tickers in shared constants config.")
    if set(tickers) != set(opening_prices):
        raise RuntimeError(
            "Ticker configuration mismatch: backend.tickers and backend.opening_prices "
            "must contain the same symbols."
        )

    return tickers, opening_prices


TICKERS, OPENING_PRICES = _load_market_constants()
