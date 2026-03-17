import asyncio
import json

from fastapi import FastAPI, WebSocket
from fastapi.encoders import jsonable_encoder

from engine.order_book import OrderBook
from engine.tickers import TICKERS
from models.client import Client


async def websocket_endpoint(
    websocket: WebSocket,
):  # Note: Place some orders before testing this
    await websocket.accept()
    try:
        summary = dict()
        print(f"Client subscribed to order book")
        while True:
            for ticker in TICKERS:
                best_bid = OrderBook.get_best_bid(ticker)
                best_ask = OrderBook.get_best_ask(ticker)
                all_bids = OrderBook.get_all_bids(ticker)
                all_asks = OrderBook.get_all_asks(ticker)
                last_price = OrderBook.get_last_price(ticker)
                last_timestamp = OrderBook.get_last_timestamp(ticker)
                pnl = OrderBook.calculate_pnl_24h(ticker)
                summary[ticker] = {
                    "ticker": ticker,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "all_bids": [
                        {
                            "order_id": order_id,
                            "timestamp": timestamp,
                            "price": price,
                            "volume": volume,
                            "stock_id": stock_id,
                        }
                        for order_id, timestamp, price, volume, stock_id in all_bids
                    ],
                    "all_asks": [
                        {
                            "order_id": order_id,
                            "timestamp": timestamp,
                            "price": price,
                            "volume": volume,
                            "stock_id": stock_id,
                        }
                        for order_id, timestamp, price, volume, stock_id in all_asks
                    ],
                    "last_price": last_price,
                    "last_timestamp": last_timestamp,
                    "pnl": pnl,
                }
            encoded = jsonable_encoder(summary)
            await websocket.send_text(json.dumps(encoded))
            await asyncio.sleep(1)  # Updates pushed every second
    except Exception as e:
        print(f"OrderBook WebSocket error: {e}")


async def client_info_websocket(websocket: WebSocket):
    """
    WebSocket endpoint to send client information (balance and portfolio).
    """
    await websocket.accept()
    try:
        # Receive the client's username from the WebSocket
        email = await websocket.receive_text()
        print(f"Client subscribed for information: {email}")

        # Fetch the client object
        client = Client.get_client_by_email(email)
        if not client:
            await websocket.send_text(
                json.dumps({"error": f"Client with email {email} not found"})
            )
            await websocket.close()
            return

        # Periodically send client information
        while True:
            pval = OrderBook.portfolio_value(client)
            pnl = {}
            portfolioPnl = OrderBook.portfolio_pnl(client)
            for ticker in TICKERS:
                pnl[ticker] = OrderBook.calculate_pnl_24h(ticker)
            client_info = {
                "balance": client.balance,
                "portfolio": client.portfolio,
                "portfolioValue": pval,
                "pnlInfo": pnl,
                "portfolioPnl": portfolioPnl,
            }
            await websocket.send_text(json.dumps(client_info))
            await asyncio.sleep(1)  # Send updates every second
    except Exception as e:
        print(f"Client Info WebSocket error: {e}")


def register_websocket_routes(app: FastAPI) -> None:
    app.websocket("/ws")(websocket_endpoint)
    app.websocket("/client_info")(client_info_websocket)
