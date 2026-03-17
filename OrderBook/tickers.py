"""Compatibility shim. Prefer importing tickers from engine.tickers."""

from engine.tickers import OPENING_PRICES, TICKERS

__all__ = ["TICKERS", "OPENING_PRICES"]
