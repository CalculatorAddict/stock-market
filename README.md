# Stock Market Simulation Backend

FastAPI-based stock market simulator with:
- in-memory order matching engine
- SQLite-backed runtime/account storage
- websocket market streams for frontend and bots
- pytest test suite split into `unit`, `api`, and `integration`

## Core functionality

- Limit and market order placement for `AAPL`, `GOOG`, `TSLA`
- Order lifecycle operations:
- `place`, `edit`, `cancel`, `status`
- Market data queries:
- best bid/ask, full book levels, volume at price
- Public transaction feed with anonymized counterparties
- Client account fetch/create by email
- WebSocket pushes for:
- global orderbook summary (`/ws`)
- per-client balance/portfolio stream (`/client_info`)
- Startup/shutdown persistence of open limit orders
- Public UUID IDs at API boundary (internal integer IDs stay private)

## Project layout

- `app.py`: ASGI entrypoint (`from app.main import app`)
- `app/main.py`: FastAPI app setup, lifespan, static mount
- `app/api.py`: REST endpoint handlers and route registration
- `app/websocket_routes.py`: websocket handlers
- `app/persistence.py`: orderbook state restore/persist
- `engine/`: order book data structure and matching engine
- `models/`: domain models (`Client`, `Order`, `Transaction`, enums)
- `TradingBot/`: websocket-driven market-making bot
- `tests/`: pytest suite (`api/`, `integration/`, `unit/`)
- `scripts/smoke_demo.sh`: quick end-to-end local smoke run

## Requirements

- Python `>=3.13`
- `uv` for environment/dependency management (recommended)

## Local setup

```bash
uv venv
source .venv/bin/activate
uv sync
```

## Run the app

```bash
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

- App root redirects to frontend at `/app`
- API lives under `/api/*`

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/place_order` | Place limit order |
| `POST` | `/api/market_order` | Place market order |
| `POST` | `/api/cancel_order` | Cancel existing order |
| `POST` | `/api/edit_order` | Edit existing order price/volume |
| `GET` | `/api/order_status` | Get order execution/cancel status |
| `GET` | `/api/get_best_bid` | Best bid for ticker |
| `GET` | `/api/get_best_ask` | Best ask for ticker |
| `GET` | `/api/get_best` | Best bid+ask snapshot |
| `GET` | `/api/get_volume_at_price` | Aggregated size at price level |
| `GET` | `/api/get_all_bids` | Full bid side levels |
| `GET` | `/api/get_all_asks` | Full ask side levels |
| `GET` | `/api/transactions` | Recent anonymized trades for ticker |
| `GET` | `/api/get_client_by_email` | Fetch client profile |
| `POST` | `/api/add_new_client` | Create/fetch client profile |

## Identity and request guardrails

Protected routes require actor identity headers:
- `X-Actor-User`
- `X-Actor-Email`

Rules:
- At least one identity header must be present for protected actions.
- Actor identity must match the target client for order/account actions.
- Ticker validation returns `404` for unknown ticker.
- Side validation returns `400` unless `buy` or `sell`.
- Non-positive price/volume inputs are rejected with `400`.

## Example requests

```bash
curl -X POST http://127.0.0.1:8000/api/place_order \
  -H "Content-Type: application/json" \
  -H "X-Actor-User: amorgan" \
  -H "X-Actor-Email: alex.morgan@demo.local" \
  -d '{
    "ticker":"AAPL",
    "side":"buy",
    "price":32.0,
    "volume":2,
    "client_user":"amorgan"
  }'
```

```bash
curl "http://127.0.0.1:8000/api/get_best?ticker=AAPL"
```

```bash
curl "http://127.0.0.1:8000/api/transactions?ticker=AAPL&limit=20"
```

## WebSocket endpoints

- `/ws`: emits periodic map of ticker summaries:
- best bid/ask, full levels, last price/timestamp, 24h pnl metric
- `/client_info`: client-specific stream
- first websocket message must be the client email
- server then emits balance, portfolio, portfolio value, pnl info

## Persistence behavior

- Uses `stock_market_database.db` and `orderbook_state` table.
- On startup:
- restores open limit orders from `orderbook_state`
- clears and rebuilds in-memory order books
- On shutdown:
- persists non-terminated open limit orders back to `orderbook_state`

This keeps runtime orderbook continuity across restarts.

## Testing

Run all tests:

```bash
uv run pytest -q
```

Run by layer:

```bash
uv run pytest -m unit -q
uv run pytest -m api -q
uv run pytest -m integration -q
```

Test layout:
- `tests/unit`: pure matching/validation logic
- `tests/api`: FastAPI TestClient + websocket API behavior
- `tests/integration`: DB/persistence/trading-bot and cross-component behavior

Notes:
- Tests isolate DB state via temporary test database wiring in `tests/conftest.py`.
- Marker config is strict (`--strict-markers`) via `pytest.ini`.

## Smoke demo

```bash
bash scripts/smoke_demo.sh
```

What it does:
- creates/updates venv
- installs dependencies
- runs tests
- starts server with `uvicorn app:app`
- calls `GET /api/get_best?ticker=AAPL`

## Trading bot

With server running:

```bash
uv run python TradingBot/TradingBot.py
```

For a more active demo market, run multiple bot profiles at once:

```bash
uv run python TradingBot/run_demo_bots.py --bot-count 2
```

Bot behavior:
- listens to `/ws`
- computes spread from recent volatility
- places buy/sell quotes through `/api/place_order`
- tracks inventory and running pnl

## Configuration

- Tickers and opening prices: `engine/tickers.py`
- Shared frontend/backend runtime constants: `static/config/shared_constants.json`
- Backend constant loader: `app/shared_constants.py`
