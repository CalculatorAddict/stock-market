import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from datetime import datetime, timedelta
from database import ensure_database_exists
from app.websocket_routes import register_websocket_routes
from app.api import register_api_routes
from app.persistence import persist_orderbook_state, restore_orderbook_state
from app.shared_constants import DEMO_CLIENTS
from engine.portfolio_value import PortfolioValue
from engine.order_book import OrderBook
from market_constants import TICKERS
from models.client import Client

# Initialize order books
order_books = [OrderBook(ticker) for ticker in TICKERS]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_database_exists(seed_clients=DEMO_CLIENTS)
    restore_orderbook_state()
    hourly_task = asyncio.create_task(update_hourly_stock_data())
    daily_task = asyncio.create_task(update_daily_portfolio_value())
    try:
        yield
    finally:
        persist_orderbook_state()
        hourly_task.cancel()
        daily_task.cancel()
        await asyncio.gather(hourly_task, daily_task, return_exceptions=True)


# Initialize the app
app = FastAPI(title="Stock Market", lifespan=lifespan)
register_websocket_routes(app)
register_api_routes(app)

# Enable CORS for frontend applications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ensure_demo_client(
    username: str,
    password: str,
    email: str,
    first_names: str,
    last_name: str,
    balance: int,
) -> Client:
    existing = Client.get_client_by_username(username)
    if existing is not None:
        existing.balance = max(existing.balance, balance)
        return existing

    return Client(username, password, email, first_names, last_name, balance=balance)


demo_clients_by_username = {}
for demo_client in DEMO_CLIENTS:
    client = _ensure_demo_client(
        demo_client["username"],
        demo_client.get("password", "pw"),
        demo_client["email"],
        demo_client.get("first_names", ""),
        demo_client.get("last_name", ""),
        balance=demo_client.get("balance", 0),
    )
    for ticker, volume in demo_client.get("portfolio", {}).items():
        client.portfolio[ticker] = volume
    demo_clients_by_username[client.username] = client

client1 = demo_clients_by_username.get("tapple")
client2 = demo_clients_by_username.get("goat")
bot = demo_clients_by_username.get("market_maker")
bot2 = demo_clients_by_username.get("market_maker2")
# client1.buy_stock(0, 0, 100)

# print(Client.get_client_by_id(0))
# print(Client.get_client_by_id(1))


# Serve static files from the "static" folder at root ("/")
app.mount("/app", StaticFiles(directory="static", html=True), name="static")


# asyncio.create_task(price_feed_loop())

# Redirect root ("/") to the static files
@app.get("/")
async def root():
    return RedirectResponse(url="/app")


async def update_hourly_stock_data():
    while True:
        now = datetime.now()
        next_hour = (now + timedelta(hours=1)).replace(
            minute=0, second=0, microsecond=0
        )
        sleep_seconds = (next_hour - now).total_seconds()
        await asyncio.sleep(sleep_seconds)
        OrderBook.update_all_last_times(next_hour)


async def update_daily_portfolio_value():
    while True:
        now = datetime.now()
        next_day = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        sleep_seconds = (next_day - now).total_seconds()
        await asyncio.sleep(sleep_seconds)
        PortfolioValue.update_all_daily_values()


# # *** Code for AR(1) price model
# import numpy as np
# # AR(1) parameters
# PHI         = 0.97
# SIGMA       = 0.3
# MIDS        = {"AAPL":180.0, "GOOG":50.0, "TSLA":12.0}
# SPREAD_BPS  = 20
# TICK_SECONDS = 0.5
# _last_price   = {ob.ticker: MIDS[ob.ticker] for ob in order_books}
# _gen_orders   = {ob.ticker: [] for ob in order_books}
# MM_CLIENT     = bot2

# # AR(1) price model
# async def price_feed_loop():
#     while True:
#         for ob in order_books:
#             sym = ob.ticker
#             prev      = _last_price[sym]
#             shock     = np.random.normal(0, SIGMA)
#             mid       = MIDS[sym] + PHI * (prev - MIDS[sym]) + shock
#             _last_price[sym] = mid

#             for oid in _gen_orders[sym]:
#                 try:
#                     OrderBook.cancel_order(oid)
#                 except Exception:
#                     pass
#             _gen_orders[sym] = []

#             half_spread = mid * SPREAD_BPS / 10_000
#             bid_px      = round(mid - half_spread, 2)
#             ask_px      = round(mid + half_spread, 2)

#             bid_id = OrderBook.place_order(sym, BUY,  bid_px, 9_999, MM_CLIENT)
#             ask_id = OrderBook.place_order(sym, SELL, ask_px, 9_999, MM_CLIENT)
#             _gen_orders[sym] = [bid_id, ask_id]

#         await asyncio.sleep(TICK_SECONDS)

# asyncio.create_task(price_feed_loop())
