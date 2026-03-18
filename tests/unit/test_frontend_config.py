import json
from pathlib import Path

from app.shared_constants import BACKEND_OPENING_PRICES, BACKEND_TICKERS
from engine.tickers import OPENING_PRICES as ENGINE_OPENING_PRICES
from engine.tickers import TICKERS as ENGINE_TICKERS
from market_constants import OPENING_PRICES as MARKET_OPENING_PRICES
from market_constants import TICKERS as MARKET_TICKERS

ROOT_DIR = Path(__file__).resolve().parents[2]


def test_market_constant_loaders_match_shared_config():
    payload = json.loads(
        (ROOT_DIR / "static" / "config" / "shared_constants.json").read_text(
            encoding="utf-8"
        )
    )
    expected_tickers = payload["backend"]["tickers"]
    expected_opening_prices = {
        ticker: float(price)
        for ticker, price in payload["backend"]["opening_prices"].items()
    }

    assert BACKEND_TICKERS == expected_tickers
    assert ENGINE_TICKERS == expected_tickers
    assert MARKET_TICKERS == expected_tickers
    assert BACKEND_OPENING_PRICES == expected_opening_prices
    assert ENGINE_OPENING_PRICES == expected_opening_prices
    assert MARKET_OPENING_PRICES == expected_opening_prices


def test_landing_preview_bootstraps_from_shared_config():
    main_js = (ROOT_DIR / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert "const LANDING_TICKERS =" not in main_js
    assert "getSharedConstants" in main_js
    assert "createLandingPreviewState(sharedConstants)" in main_js
