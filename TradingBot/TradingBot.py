import argparse
import asyncio
import json
import random
import sys
from datetime import datetime
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import requests
import websockets


class TradingBot:
    @staticmethod
    def log(message):
        print(message, flush=True)

    @staticmethod
    def load_demo_accounts():
        config_path = (
            Path(__file__).resolve().parent.parent
            / "static"
            / "config"
            / "shared_constants.json"
        )
        try:
            with config_path.open() as config_file:
                shared_constants = json.load(config_file)
            accounts = shared_constants.get("backend", {}).get("demo_clients", [])
            return {
                account["username"]: account
                for account in accounts
                if "username" in account
            }
        except Exception:
            return {}

    def __init__(
        self,
        client_user: str = "market_maker",
        client_email: str | None = None,
        api_url: str = "http://localhost:8000/api/place_order",
        websocket_url: str = "ws://localhost:8000/ws",
        actor_user_header: str = "X-Actor-User",
        actor_email_header: str = "X-Actor-Email",
        min_quote_size: int = 1,
        max_quote_size: int = 5,
        min_trade_interval: float = 0.5,
        max_trade_interval: float = 1.5,
        spread_range: tuple[float, float] = (0.01, 0.03),
        bias_probability: float = 0.2,
        cross_probability: float = 0.15,
        cancel_probability: float = 0.3,
        quote_noise_range: tuple[float, float] = (-0.005, 0.005),
        include_email_header: bool = False,
        auto_start: bool = True,
    ):
        self.demo_accounts = self.load_demo_accounts()
        account = self.demo_accounts.get(client_user)
        self.client_user = client_user
        resolved_email = account.get("email") if account else None
        if client_email and resolved_email and client_email != resolved_email:
            self.log(
                f"Bot identity mismatch for {client_user}: "
                f"overriding email {client_email} with {resolved_email}"
            )
        self.client_email = resolved_email or client_email
        self.api_url = api_url
        self.websocket_url = websocket_url
        self.actor_user_header = actor_user_header
        self.actor_email_header = actor_email_header
        self.include_email_header = include_email_header
        self.running = True
        self.ticker_states = defaultdict(
            lambda: {
                "inventory": 0,
                "price_history": [],
                "last_trade_time": datetime.now(),
                "last_price": None,
                "total_pnl": 0,
                "trades": [],
                "open_orders": {"buy": {}, "sell": {}},
                "next_order_time": datetime.now(),
                "inventory_loaded": False,
            }
        )
        self.base_size = 50
        self.min_quote_size = min_quote_size
        self.max_quote_size = max_quote_size
        self.volatility_window = 20
        self.min_trade_interval = min_trade_interval
        self.max_trade_interval = max_trade_interval
        self.spread_range = spread_range
        self.min_spread = self.spread_range[0]
        self.bias_probability = bias_probability
        self.cross_probability = cross_probability
        self.cancel_probability = cancel_probability
        self.quote_noise_range = quote_noise_range
        self.cancel_url = f"{self.api_url.rsplit('/', 1)[0]}/cancel_order"
        if auto_start:
            self.run()

    def run(self):
        try:
            self.log(
                f"Initialising {self.client_user} "
                f"(email={self.client_email or 'none'}, "
                f"include_email_header={self.include_email_header})"
            )
            asyncio.run(self.listen_orderbook())
        except KeyboardInterrupt:
            self.handle_shutdown()
        except Exception as e:
            self.log(f"Error initialising {self.client_user}: {e}")
            raise

    def handle_shutdown(self):
        if not self.running:
            return
        self.running = False
        print("FINAL PERFORMANCE SUMMARY:")
        total_pnl = 0
        total_trades = 0

        plt.figure(figsize=(12, 6))

        for ticker, state in self.ticker_states.items():
            if state["trades"]:
                print(f"\n{ticker}:")
                print(f"  PnL: {state['total_pnl']}")
                print(f"  Trades: {len(state['trades'])}")
                print(f"  Final Inventory: {state['inventory']}")
                total_pnl += state["total_pnl"]
                total_trades += len(state["trades"])
                timestamps = [trade["timestamp"] for trade in state["trades"]]
                running_pnl = []
                current_pnl = 0
                for trade in state["trades"]:
                    current_pnl += trade["pnl"]
                    running_pnl.append(current_pnl)
                plt.plot(
                    timestamps, running_pnl, label=ticker, marker="o", markersize=2
                )

        print("\nOverall Performance:")
        print(f"PnL: {total_pnl}")
        print(f"Total Trades: {total_trades}")

        plt.title("Total PnL Over Time")
        plt.xlabel("Time")
        plt.ylabel("Total PnL ($)")
        plt.grid(True)
        plt.legend()
        plt.xticks(rotation=45)
        plt.tight_layout()

        # plot_path = os.path.join(os.path.dirname(__file__), "trading_performance.png")
        # plt.savefig(plot_path)
        # print(f"\nPlot saved to: {plot_path}")

        sys.exit(0)

    def log_status(self, ticker):
        state = self.ticker_states[ticker]
        print(f"PORTFOLIO FOR {ticker}:")
        print(f"Current Inventory: {state['inventory']} shares")
        print(f"PnL: {state['total_pnl']}")
        print(
            f"Current Position Value: {state['inventory'] * state['last_price'] if state['last_price'] else 0}"
        )
        print("\n")

    def request_headers(self):
        headers = {self.actor_user_header: self.client_user}
        if self.include_email_header and self.client_email:
            headers[self.actor_email_header] = self.client_email
        return headers

    def load_inventory(self, ticker):
        state = self.ticker_states[ticker]
        if state["inventory_loaded"]:
            return

        try:
            account = self.demo_accounts.get(self.client_user)
            if account is not None:
                state["inventory"] = int(account.get("portfolio", {}).get(ticker, 0))
        except Exception:
            pass

        state["inventory_loaded"] = True

    def round_price(self, price):
        return round(max(price, 0.01), 2)

    def quote_volume(self):
        return random.randint(self.min_quote_size, self.max_quote_size)

    def next_delay(self):
        return random.uniform(self.min_trade_interval, self.max_trade_interval)

    def reference_price(self, best_bid, best_ask, last_price):
        if best_bid not in (None, 0) and best_ask not in (None, 0):
            return (best_bid + best_ask) / 2
        if last_price and last_price > 0:
            return last_price
        if best_bid not in (None, 0):
            return best_bid
        if best_ask not in (None, 0):
            return best_ask
        return 100.0

    def tracked_sell_volume(self, ticker):
        return sum(
            order["remaining_volume"]
            for order in self.ticker_states[ticker]["open_orders"]["sell"].values()
        )

    def available_inventory(self, ticker):
        state = self.ticker_states[ticker]
        return max(0, state["inventory"] - self.tracked_sell_volume(ticker))

    def record_fill(self, ticker, side, price, volume):
        if volume <= 0:
            return

        state = self.ticker_states[ticker]
        pnl = 0
        if side == "buy":
            state["inventory"] += volume
            pnl = -price * volume
        else:
            state["inventory"] = max(0, state["inventory"] - volume)
            pnl = price * volume

        state["total_pnl"] += pnl
        state["last_trade_time"] = datetime.now()
        state["trades"].append(
            {
                "timestamp": datetime.now(),
                "side": side,
                "price": price,
                "volume": volume,
                "pnl": pnl,
            }
        )
        print(f"\nTRADE EXECUTED FOR {ticker}:")
        print(f"Side: {side}")
        print(f"Price: {price}")
        print(f"Volume: {volume}")
        print(f"PnL: {pnl}")

    def reconcile_open_orders(self, ticker, data):
        state = self.ticker_states[ticker]
        active_orders = {
            "buy": {order["order_id"]: order for order in data.get("all_bids", [])},
            "sell": {order["order_id"]: order for order in data.get("all_asks", [])},
        }

        for side in ("buy", "sell"):
            tracked_orders = state["open_orders"][side]
            for order_id, tracked_order in list(tracked_orders.items()):
                current_order = active_orders[side].get(order_id)
                if current_order is None:
                    self.record_fill(
                        ticker,
                        side,
                        tracked_order["price"],
                        tracked_order["remaining_volume"],
                    )
                    tracked_orders.pop(order_id, None)
                    continue

                filled_volume = (
                    tracked_order["remaining_volume"] - current_order["volume"]
                )
                if filled_volume > 0:
                    self.record_fill(
                        ticker, side, tracked_order["price"], filled_volume
                    )
                tracked_order["remaining_volume"] = current_order["volume"]

    def quote_prices(self, best_bid, best_ask, last_price):
        reference = self.reference_price(best_bid, best_ask, last_price)
        spread = random.uniform(*self.spread_range)
        buy_price = reference * (1 - spread / 2)
        sell_price = reference * (1 + spread / 2)

        bias = None
        if random.random() < self.bias_probability:
            bias = random.choice(["up", "down"])
            aggression = random.uniform(0.15, 0.35)
            if bias == "up":
                buy_price = reference * (1 - spread * aggression)
            else:
                sell_price = reference * (1 + spread * aggression)

        noise = random.uniform(*self.quote_noise_range)
        buy_price *= 1 + noise
        sell_price *= 1 + noise

        cross_side = None
        if (
            best_bid not in (None, 0)
            and best_ask not in (None, 0)
            and random.random() < self.cross_probability
        ):
            cross_side = random.choice(["buy", "sell"])
            if cross_side == "buy":
                buy_price = best_ask * (1 + random.uniform(0.001, 0.005))
                sell_price = max(
                    sell_price,
                    buy_price * (1 + random.uniform(0.003, 0.01)),
                )
            else:
                sell_price = best_bid * (1 - random.uniform(0.001, 0.005))
                buy_price = min(
                    buy_price,
                    sell_price * (1 - random.uniform(0.003, 0.01)),
                )

        buy_price = self.round_price(buy_price)
        sell_price = self.round_price(sell_price)

        if cross_side is None and sell_price <= buy_price:
            sell_price = self.round_price(buy_price + 0.01)

        return buy_price, sell_price, spread, bias, cross_side

    async def cancel_order(self, ticker, side, order_id):
        payload = {"order_id": order_id}
        headers = self.request_headers()

        def send_request():
            try:
                response = requests.post(self.cancel_url, json=payload, headers=headers)
                if response.status_code == 200:
                    self.log(f"Cancelled {side} order for {ticker}: {order_id}")
                    return True
                if response.status_code == 404:
                    self.log(f"Order already absent for {ticker}: {order_id}")
                    return True
                self.log(
                    f"Failed to cancel order for {ticker}: status={response.status_code} "
                    f"actor_user={self.client_user} order_id={order_id} "
                    f"body={response.text}"
                )
            except Exception as e:
                self.log(f"Connection error cancelling order for {ticker}: {e}")
            return False

        cancelled = await asyncio.to_thread(send_request)
        if cancelled:
            self.ticker_states[ticker]["open_orders"][side].pop(order_id, None)
        return cancelled

    async def cancel_orders_for_side(self, ticker, side):
        open_orders = list(self.ticker_states[ticker]["open_orders"][side])
        for order_id in open_orders:
            await self.cancel_order(ticker, side, order_id)

    async def randomly_cancel_orders(self, ticker):
        state = self.ticker_states[ticker]
        for side in ("buy", "sell"):
            for order_id in list(state["open_orders"][side]):
                if random.random() < self.cancel_probability:
                    await self.cancel_order(ticker, side, order_id)

    async def listen_orderbook(self):
        uri = self.websocket_url
        async with websockets.connect(uri) as websocket:
            while self.running:
                try:
                    msg = await websocket.recv()
                    data = json.loads(msg)
                    for ticker, ticker_data in data.items():
                        await self.market_make(ticker, ticker_data)
                except websockets.exceptions.ConnectionClosed:
                    print("WebSocket connection closed")
                    break
                except Exception as e:
                    print(f"Error processing message: {e}")
                    continue

    def volatility(self, ticker):
        price_history = self.ticker_states[ticker]["price_history"]
        if len(price_history) < self.volatility_window:
            return 0.1
        returns = np.diff(np.log(price_history[-self.volatility_window :]))
        return np.std(returns) * np.sqrt(252)

    async def market_make(self, ticker, data):
        best_bid = data["best_bid"]
        best_ask = data["best_ask"]
        last_price = data["last_price"]
        state = self.ticker_states[ticker]
        self.load_inventory(ticker)
        self.reconcile_open_orders(ticker, data)

        reference = self.reference_price(best_bid, best_ask, last_price)
        state["price_history"].append(reference)
        state["last_price"] = reference

        # Empty books now surface as None (legacy deployments may still send 0).
        if best_bid in (None, 0) and best_ask in (None, 0):
            print(f"\nInitialising market for {ticker}")
            bid_price, ask_price, spread, _, _ = self.quote_prices(
                best_bid, best_ask, last_price
            )
            buy_volume = self.quote_volume()
            sell_volume = min(self.quote_volume(), self.available_inventory(ticker))
            await self.cancel_orders_for_side(ticker, "buy")
            await self.cancel_orders_for_side(ticker, "sell")
            await self.place_order(ticker, "buy", bid_price, buy_volume)
            if sell_volume > 0:
                await self.place_order(ticker, "sell", ask_price, sell_volume)
            state["next_order_time"] = datetime.now() + timedelta(
                seconds=self.next_delay()
            )
            print(f"Placed initial orders for {ticker}:")
            print(f"Bid: {bid_price} x {buy_volume}")
            print(f"Ask: {ask_price} x {sell_volume}")
            print(f"Spread: {spread:.2%}")
            return

        if datetime.now() < state["next_order_time"]:
            return

        await self.randomly_cancel_orders(ticker)
        buy_price, sell_price, spread, bias, cross_side = self.quote_prices(
            best_bid, best_ask, last_price
        )
        buy_volume = self.quote_volume()
        sell_volume = min(self.quote_volume(), self.available_inventory(ticker))

        side_sequence = ["buy", "sell"] if cross_side != "sell" else ["sell", "buy"]
        order_plan = {
            "buy": (buy_price, buy_volume),
            "sell": (sell_price, sell_volume),
        }

        for side in side_sequence:
            if side == "sell" and order_plan[side][1] <= 0:
                continue
            await self.cancel_orders_for_side(ticker, side)
            price, volume = order_plan[side]
            await self.place_order(ticker, side, price, volume)

        state["next_order_time"] = datetime.now() + timedelta(seconds=self.next_delay())
        print(
            f"{ticker} quotes refreshed at {reference:.2f} with spread {spread:.2%}, "
            f"bias={bias or 'none'}, cross={cross_side or 'none'}"
        )
        self.log_status(ticker)

    async def place_order(self, ticker, side, price, volume):
        payload = {
            "ticker": ticker,
            "side": side,
            "price": price,
            "volume": volume,
            "client_user": self.client_user,
        }
        headers = self.request_headers()

        def send_request():
            try:
                response = requests.post(self.api_url, json=payload, headers=headers)
                if response.status_code == 200:
                    order_id = None
                    try:
                        order_id = response.json()
                    except Exception:
                        order_id = None

                    if isinstance(order_id, str):
                        self.ticker_states[ticker]["open_orders"][side][order_id] = {
                            "price": price,
                            "remaining_volume": volume,
                        }
                    print(f"\nORDER PLACED FOR {ticker}:")
                    print(f"Side: {side}")
                    print(f"Price: {price}")
                    print(f"Volume: {volume}")
                else:
                    self.log(
                        f"Failed to place order for {ticker}: status={response.status_code} "
                        f"actor_user={self.client_user} payload_client_user={self.client_user} "
                        f"body={response.text}"
                    )
            except Exception as e:
                self.log(f"Connection error placing order for {ticker}: {e}")

        await asyncio.to_thread(send_request)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-user", default="market_maker")
    parser.add_argument("--client-email")
    parser.add_argument("--api-url", default="http://localhost:8000/api/place_order")
    parser.add_argument("--websocket-url", default="ws://localhost:8000/ws")
    parser.add_argument("--min-quote-size", type=int, default=1)
    parser.add_argument("--max-quote-size", type=int, default=5)
    parser.add_argument("--min-interval", type=float, default=0.5)
    parser.add_argument("--max-interval", type=float, default=1.5)
    parser.add_argument("--min-spread", type=float, default=0.01)
    parser.add_argument("--max-spread", type=float, default=0.03)
    parser.add_argument("--bias-probability", type=float, default=0.2)
    parser.add_argument("--cross-probability", type=float, default=0.15)
    parser.add_argument("--cancel-probability", type=float, default=0.3)
    parser.add_argument("--include-email-header", action="store_true")
    args = parser.parse_args()

    TradingBot(
        client_user=args.client_user,
        client_email=args.client_email,
        api_url=args.api_url,
        websocket_url=args.websocket_url,
        min_quote_size=args.min_quote_size,
        max_quote_size=args.max_quote_size,
        min_trade_interval=args.min_interval,
        max_trade_interval=args.max_interval,
        spread_range=(args.min_spread, args.max_spread),
        bias_probability=args.bias_probability,
        cross_probability=args.cross_probability,
        cancel_probability=args.cancel_probability,
        include_email_header=args.include_email_header,
    )
