"""Concrete market-making bot implementation for the demo exchange."""

import argparse
import asyncio
import random
import sys
from collections import defaultdict
from datetime import datetime
from datetime import timedelta

import matplotlib.pyplot as plt
import numpy as np
import requests

from trading_bot import TradingBot


class MarketMaker(TradingBot):
    """Automated trader that maintains two-sided quotes for each ticker."""

    def __init__(
        self,
        client_user: str | None = None,
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
        """Initialise the market-making strategy and its per-ticker state."""
        super().__init__(
            client_user=client_user,
            client_email=client_email,
            api_url=api_url,
            websocket_url=websocket_url,
            actor_user_header=actor_user_header,
            actor_email_header=actor_email_header,
            include_email_header=include_email_header,
        )
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
        if auto_start:
            self.run()

    def handle_shutdown(self):
        """Print a final trading summary and exit the process."""
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
        """Print the current position, mark value, and PnL for one ticker."""
        state = self.ticker_states[ticker]
        print(f"PORTFOLIO FOR {ticker}:")
        print(f"Current Inventory: {state['inventory']} shares")
        print(f"PnL: {state['total_pnl']}")
        print(
            f"Current Position Value: {state['inventory'] * state['last_price'] if state['last_price'] else 0}"
        )
        print("\n")

    def load_inventory(self, ticker):
        """Seed local inventory state for a ticker from the bot account config."""
        state = self.ticker_states[ticker]
        if state["inventory_loaded"]:
            return

        try:
            account = self.bot_accounts.get(self.client_user)
            if account is not None:
                state["inventory"] = int(account.get("portfolio", {}).get(ticker, 0))
        except Exception:
            pass

        state["inventory_loaded"] = True

    def round_price(self, price):
        """Clamp to a positive market price and round to cents."""
        return round(max(price, 0.01), 2)

    def quote_volume(self):
        """Sample an order size within the configured quoting range."""
        return random.randint(self.min_quote_size, self.max_quote_size)

    def next_delay(self):
        """Sample the delay before the next quote refresh."""
        return random.uniform(self.min_trade_interval, self.max_trade_interval)

    def reference_price(self, best_bid, best_ask, last_price):
        """Choose a quoting anchor from the book, last trade, or a default price."""
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
        """Return the sell volume already committed in open orders for a ticker."""
        return sum(
            order["remaining_volume"]
            for order in self.ticker_states[ticker]["open_orders"]["sell"].values()
        )

    def tracked_orders_for_side(self, ticker, side):
        """Return tracked orders for one side of a ticker."""
        return self.ticker_states[ticker]["open_orders"][side]

    def tracked_order(self, ticker, side):
        """Return the single tracked order for a side, if any."""
        orders = self.tracked_orders_for_side(ticker, side)
        return next(iter(orders.items()), (None, None))

    def track_order(self, ticker, side, order_id, price, volume, total_volume=None):
        """Replace tracked state so a side has at most one order."""
        self.ticker_states[ticker]["open_orders"][side] = {
            order_id: {
                "price": price,
                "remaining_volume": volume,
                "total_volume": volume if total_volume is None else total_volume,
            }
        }

    def available_inventory(self, ticker):
        """Return inventory that can still be offered for sale."""
        state = self.ticker_states[ticker]
        return max(0, state["inventory"] - self.tracked_sell_volume(ticker))

    def available_inventory_for_side(self, ticker, side):
        """Return inventory available for a new or replacement order on one side."""
        if side != "sell":
            return 0

        _, tracked_order = self.tracked_order(ticker, side)
        tracked_volume = (
            tracked_order["remaining_volume"] if tracked_order is not None else 0
        )
        return self.available_inventory(ticker) + tracked_volume

    def record_fill(self, ticker, side, price, volume):
        """Update inventory, PnL, and fill history after an executed trade."""
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
        """Match tracked orders against the latest book snapshot and detect fills."""
        state = self.ticker_states[ticker]
        active_orders = {
            "buy": {order["order_id"]: order for order in data.get("all_bids", [])},
            "sell": {order["order_id"]: order for order in data.get("all_asks", [])},
        }

        for side in ("buy", "sell"):
            tracked_orders = state["open_orders"][side]
            for order_id, tracked_order in list(tracked_orders.items()):
                tracked_order.setdefault(
                    "total_volume", tracked_order["remaining_volume"]
                )
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

    async def prune_extra_orders_for_side(self, ticker, side):
        """Cancel any surplus tracked orders so each side keeps one live order."""
        tracked_orders = list(self.tracked_orders_for_side(ticker, side))
        for order_id in tracked_orders[1:]:
            await self.cancel_order(ticker, side, order_id)

    def quote_prices(self, best_bid, best_ask, last_price):
        """Generate buy and sell quotes with spread, bias, and crossing logic."""
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
        """Cancel one outstanding order through the HTTP API."""
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
        """Cancel all tracked open orders for one side of a ticker."""
        open_orders = list(self.tracked_orders_for_side(ticker, side))
        for order_id in open_orders:
            await self.cancel_order(ticker, side, order_id)

    async def randomly_cancel_orders(self, ticker):
        """Randomly cancel existing quotes to keep the bot from staying static."""
        state = self.ticker_states[ticker]
        for side in ("buy", "sell"):
            for order_id in list(state["open_orders"][side]):
                if random.random() < self.cancel_probability:
                    await self.cancel_order(ticker, side, order_id)

    async def edit_order(self, ticker, side, order_id, price, volume):
        """Edit one outstanding order through the HTTP API."""
        tracked_order = self.tracked_orders_for_side(ticker, side).get(order_id)
        if tracked_order is None:
            return "missing"

        total_volume = tracked_order.get(
            "total_volume", tracked_order["remaining_volume"]
        )
        executed_volume = total_volume - tracked_order["remaining_volume"]
        payload = {
            "order_id": order_id,
            "price": price,
            "volume": executed_volume + volume,
        }
        headers = self.request_headers()

        def send_request():
            try:
                response = requests.post(self.edit_url, json=payload, headers=headers)
                if response.status_code == 200:
                    self.track_order(
                        ticker,
                        side,
                        order_id,
                        price,
                        volume,
                        total_volume=payload["volume"],
                    )
                    self.log(f"Edited {side} order for {ticker}: {order_id}")
                    return "edited"
                if response.status_code == 404:
                    self.log(f"Order already absent for {ticker}: {order_id}")
                    return "missing"
                self.log(
                    f"Failed to edit order for {ticker}: status={response.status_code} "
                    f"actor_user={self.client_user} order_id={order_id} "
                    f"body={response.text}"
                )
            except Exception as e:
                self.log(f"Connection error editing order for {ticker}: {e}")
            return "failed"

        result = await asyncio.to_thread(send_request)
        if result == "missing":
            self.ticker_states[ticker]["open_orders"][side].pop(order_id, None)
        return result

    async def upsert_quote(self, ticker, side, price, volume):
        """Maintain at most one live order per side and edit in place when needed."""
        await self.prune_extra_orders_for_side(ticker, side)

        if volume <= 0:
            await self.cancel_orders_for_side(ticker, side)
            return

        order_id, tracked_order = self.tracked_order(ticker, side)
        if tracked_order is None:
            await self.place_order(ticker, side, price, volume)
            return

        if (
            tracked_order["price"] == price
            and tracked_order["remaining_volume"] == volume
        ):
            return

        result = await self.edit_order(ticker, side, order_id, price, volume)
        if result == "missing":
            await self.place_order(ticker, side, price, volume)

    def volatility(self, ticker):
        """Estimate annualised volatility from recent reference-price history."""
        price_history = self.ticker_states[ticker]["price_history"]
        if len(price_history) < self.volatility_window:
            return 0.1
        returns = np.diff(np.log(price_history[-self.volatility_window :]))
        return np.std(returns) * np.sqrt(252)

    async def process_market_update(self, ticker, data):
        """Refresh quotes for a ticker based on the latest book snapshot."""
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
            sell_volume = min(
                self.quote_volume(),
                self.available_inventory_for_side(ticker, "sell"),
            )
            await self.upsert_quote(ticker, "buy", bid_price, buy_volume)
            await self.upsert_quote(ticker, "sell", ask_price, sell_volume)
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
        sell_volume = min(
            self.quote_volume(),
            self.available_inventory_for_side(ticker, "sell"),
        )

        side_sequence = ["buy", "sell"] if cross_side != "sell" else ["sell", "buy"]
        order_plan = {
            "buy": (buy_price, buy_volume),
            "sell": (sell_price, sell_volume),
        }

        for side in side_sequence:
            price, volume = order_plan[side]
            await self.upsert_quote(ticker, side, price, volume)

        state["next_order_time"] = datetime.now() + timedelta(seconds=self.next_delay())
        print(
            f"{ticker} quotes refreshed at {reference:.2f} with spread {spread:.2%}, "
            f"bias={bias or 'none'}, cross={cross_side or 'none'}"
        )
        self.log_status(ticker)

    async def place_order(self, ticker, side, price, volume):
        """Submit an order through the HTTP API and track it if accepted."""
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
                        self.track_order(ticker, side, order_id, price, volume)
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
    parser.add_argument("--client-user", default=None)
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
    args = parser.parse_args()

    MarketMaker(
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
    )
