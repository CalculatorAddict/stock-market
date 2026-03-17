import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from OrderBook.OrderBook import *
from OrderBook.tickers import *
from datetime import datetime, timedelta
from app.websocket_routes import register_websocket_routes
from app.api import register_api_routes

# Initialize the app
app = FastAPI(title="Stock Market")
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

# Initialize order books
order_books = [OrderBook(ticker) for ticker in TICKERS]


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


client1 = _ensure_demo_client(
    "tapple", "pw", "timcook@aol.com", "Tim", "Cook", balance=1_000_000_000
)
client2 = _ensure_demo_client(
    "goat", "pw", "lbj@nba.com", "LeBron", "James", balance=1_000_000_000
)
bot = _ensure_demo_client(
    "market_maker",
    "pw",
    "market_maker@gmail.com",
    "Market",
    "Maker",
    balance=1_000_000_000,
)
bot2 = _ensure_demo_client(
    "market_maker2",
    "pw",
    "market_maker2@gmail.com",
    "Market",
    "Maker2",
    balance=1_000_000_000,
)

client1.portfolio["AAPL"] = 1000
client2.portfolio["AAPL"] = 1000
bot.portfolio["AAPL"] = 1000
bot2.portfolio["AAPL"] = 1000
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
        Client.update_all_daily_portfolio()


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(update_hourly_stock_data())
    asyncio.create_task(update_daily_portfolio_value())


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
