"""Abstract interface and shared lifecycle for automated trading bots."""

import asyncio
import json
from abc import ABC, abstractmethod
from pathlib import Path

import websockets


class TradingBot(ABC):
    """Base contract for bots that consume order book updates over websockets."""

    @staticmethod
    def log(message):
        """Print a log line immediately so bot output stays visible in real time."""
        print(message, flush=True)

    @staticmethod
    def load_bot_accounts():
        """Load configured demo bot accounts from the shared frontend constants."""
        config_path = (
            Path(__file__).resolve().parent.parent
            / "static"
            / "config"
            / "shared_constants.json"
        )
        try:
            with config_path.open() as config_file:
                shared_constants = json.load(config_file)
            accounts = shared_constants.get("backend", {}).get("bot_clients", [])
            return {
                account["username"]: account
                for account in accounts
                if "username" in account
            }
        except Exception:
            return {}

    @classmethod
    def default_bot_username(cls):
        """Return the first configured bot username or a safe fallback."""
        accounts = cls.load_bot_accounts()
        return next(iter(accounts), "demo_bot")

    def __init__(
        self,
        client_user: str | None = None,
        client_email: str | None = None,
        api_url: str = "http://localhost:8000/api/place_order",
        websocket_url: str = "ws://localhost:8000/ws",
        actor_user_header: str = "X-Actor-User",
        actor_email_header: str = "X-Actor-Email",
        include_email_header: bool = False,
    ):
        """Initialise shared API and identity settings for a concrete bot."""
        self.bot_accounts = self.load_bot_accounts()
        if client_user is None:
            client_user = self.default_bot_username()
        account = self.bot_accounts.get(client_user)
        self.client_user = client_user
        resolved_email = account.get("email") if account else None
        self.client_email = resolved_email or client_email
        self.api_url = api_url
        self.websocket_url = websocket_url
        self.actor_user_header = actor_user_header
        self.actor_email_header = actor_email_header
        self.include_email_header = include_email_header
        self.cancel_url = f"{self.api_url.rsplit('/', 1)[0]}/cancel_order"
        self.edit_url = f"{self.api_url.rsplit('/', 1)[0]}/edit_order"
        self.running = True

    def run(self):
        """Start the websocket listener and keep running until interrupted."""
        try:
            self.log(
                f"Initialising {self.client_user} "
                f"(email={self.client_email or 'none'}, "
                f"include_email_header={self.include_email_header})"
            )
            asyncio.run(self.listen_orderbook())
        except KeyboardInterrupt:
            self.handle_shutdown()
        except Exception as error:
            self.log(f"Error initialising {self.client_user}: {error}")
            raise

    def request_headers(self):
        """Build request headers for acting as the configured bot user."""
        headers = {self.actor_user_header: self.client_user}
        if self.include_email_header and self.client_email:
            headers[self.actor_email_header] = self.client_email
        return headers

    async def listen_orderbook(self):
        """Consume websocket order book snapshots and delegate processing."""
        async with websockets.connect(self.websocket_url) as websocket:
            while self.running:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    for ticker, ticker_data in data.items():
                        await self.process_market_update(ticker, ticker_data)
                except websockets.exceptions.ConnectionClosed:
                    print("WebSocket connection closed")
                    break
                except Exception as error:
                    print(f"Error processing message: {error}")
                    continue

    @abstractmethod
    def handle_shutdown(self):
        """Clean up and emit final strategy-specific output before exit."""

    @abstractmethod
    async def process_market_update(self, ticker, data):
        """React to a single ticker update from the order book stream."""
