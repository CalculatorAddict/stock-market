import json
from pathlib import Path


DEFAULT_SHARED_CONSTANTS = {
    "identity_headers": {
        "user": "X-Actor-User",
        "email": "X-Actor-Email",
    },
    "frontend": {
        "google_client_id": "933623916878-ipovfk31uqvoidtvj5pcknkod3ggdter.apps.googleusercontent.com",
        "websocket": {
            "client_info_primary": "ws://localhost:8000/client_info",
            "client_info_fallback": "ws://mtomecki.pl:8000/client_info",
            "orderbook_primary": "ws://localhost:8000/ws",
            "orderbook_fallback": "ws://mtomecki.pl:8000/ws",
        },
    },
    "backend": {
        "demo": {
            "title": "Demo access",
            "description": (
                "Use these demo users to place sample orders in the local environment."
            ),
            "default_ticker": "AAPL",
        },
        "demo_clients": [
            {
                "username": "tapple",
                "password": "pw",
                "email": "timcook@aol.com",
                "first_names": "Tim",
                "last_name": "Cook",
                "balance": 1_000_000_000,
                "portfolio": {"AAPL": 1000},
            },
            {
                "username": "goat",
                "password": "pw",
                "email": "lbj@nba.com",
                "first_names": "LeBron",
                "last_name": "James",
                "balance": 1_000_000_000,
                "portfolio": {"AAPL": 1000},
            },
            {
                "username": "market_maker",
                "password": "pw",
                "email": "market_maker@gmail.com",
                "first_names": "Market",
                "last_name": "Maker",
                "balance": 1_000_000_000,
                "portfolio": {"AAPL": 1000},
            },
            {
                "username": "market_maker2",
                "password": "pw",
                "email": "market_maker2@gmail.com",
                "first_names": "Market",
                "last_name": "Maker2",
                "balance": 1_000_000_000,
                "portfolio": {"AAPL": 1000},
            },
        ],
    },
}


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
    except Exception:
        return DEFAULT_SHARED_CONSTANTS


SHARED_CONSTANTS = _load_shared_constants()
IDENTITY_HEADER_USER = SHARED_CONSTANTS.get("identity_headers", {}).get(
    "user", DEFAULT_SHARED_CONSTANTS["identity_headers"]["user"]
)
IDENTITY_HEADER_EMAIL = SHARED_CONSTANTS.get("identity_headers", {}).get(
    "email", DEFAULT_SHARED_CONSTANTS["identity_headers"]["email"]
)

GOOGLE_CLIENT_ID = SHARED_CONSTANTS.get("frontend", {}).get(
    "google_client_id", DEFAULT_SHARED_CONSTANTS["frontend"]["google_client_id"]
)

CLIENT_INFO_WS_PRIMARY = (
    SHARED_CONSTANTS.get("frontend", {})
    .get("websocket", {})
    .get(
        "client_info_primary",
        DEFAULT_SHARED_CONSTANTS["frontend"]["websocket"]["client_info_primary"],
    )
)
CLIENT_INFO_WS_FALLBACK = (
    SHARED_CONSTANTS.get("frontend", {})
    .get("websocket", {})
    .get(
        "client_info_fallback",
        DEFAULT_SHARED_CONSTANTS["frontend"]["websocket"]["client_info_fallback"],
    )
)
ORDERBOOK_WS_PRIMARY = (
    SHARED_CONSTANTS.get("frontend", {})
    .get("websocket", {})
    .get(
        "orderbook_primary",
        DEFAULT_SHARED_CONSTANTS["frontend"]["websocket"]["orderbook_primary"],
    )
)
ORDERBOOK_WS_FALLBACK = (
    SHARED_CONSTANTS.get("frontend", {})
    .get("websocket", {})
    .get(
        "orderbook_fallback",
        DEFAULT_SHARED_CONSTANTS["frontend"]["websocket"]["orderbook_fallback"],
    )
)

DEMO_CLIENTS = SHARED_CONSTANTS.get("backend", {}).get(
    "demo_clients",
    DEFAULT_SHARED_CONSTANTS["backend"]["demo_clients"],
)

DEMO_API_INFO = SHARED_CONSTANTS.get("backend", {}).get(
    "demo",
    DEFAULT_SHARED_CONSTANTS["backend"]["demo"],
)
