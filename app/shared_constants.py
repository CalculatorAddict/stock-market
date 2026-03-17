import json
from pathlib import Path


def _load_shared_constants() -> dict:
    constants_path = (
        Path(__file__).resolve().parent.parent
        / "static"
        / "config"
        / "shared_constants.json"
    )
    try:
        with constants_path.open("r", encoding="utf-8") as file_handle:
            return json.load(file_handle)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load shared constants from {constants_path}"
        ) from exc


def _required(path: str):
    current = SHARED_CONSTANTS
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            raise RuntimeError(f"Missing required shared constant: {path}")
        current = current[key]
    return current


SHARED_CONSTANTS = _load_shared_constants()
IDENTITY_HEADER_USER = _required("identity_headers.user")
IDENTITY_HEADER_EMAIL = _required("identity_headers.email")
GOOGLE_CLIENT_ID = _required("frontend.google_client_id")
CLIENT_INFO_WS_PRIMARY = _required("frontend.websocket.client_info_primary")
CLIENT_INFO_WS_FALLBACK = _required("frontend.websocket.client_info_fallback")
ORDERBOOK_WS_PRIMARY = _required("frontend.websocket.orderbook_primary")
ORDERBOOK_WS_FALLBACK = _required("frontend.websocket.orderbook_fallback")
BACKEND_TICKERS = _required("backend.tickers")
BACKEND_OPENING_PRICES = _required("backend.opening_prices")
DEMO_CLIENTS = _required("backend.demo_clients")
DEMO_API_INFO = _required("backend.demo")
