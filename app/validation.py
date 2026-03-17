from fastapi import HTTPException

from OrderBook.tickers import TICKERS


def validate_ticker(ticker: str) -> str:
    if ticker not in TICKERS:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")
    return ticker


def validate_side(side: str) -> str:
    normalized = side.lower()
    if normalized not in {"buy", "sell"}:
        raise HTTPException(
            status_code=400, detail="Invalid side. Must be either 'buy' or 'sell'."
        )
    return normalized


def orderbook_error_to_http(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc
