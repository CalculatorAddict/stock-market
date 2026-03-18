import asyncio
import json
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket
from fastapi.encoders import jsonable_encoder
from starlette.websockets import WebSocketDisconnect
from pydantic import ValidationError

from app.client_info_auth import authenticate_client_info_token
from app.id_codec import to_public_order_id
from app.schemas import ClientInfoWebSocketSubscription
from engine.order_book import OrderBook
from engine.portfolio_value import PortfolioValue
from market_constants import TICKERS


async def websocket_endpoint(
    websocket: WebSocket,
):  # Note: Place some orders before testing this
    await websocket.accept()
    try:
        summary = dict()
        print(f"Client subscribed to order book")
        while True:
            server_time = datetime.now(timezone.utc)
            for ticker in TICKERS:
                best_bid = OrderBook.get_best_bid(ticker)
                best_ask = OrderBook.get_best_ask(ticker)
                all_bids = OrderBook.get_all_bids(ticker)
                all_asks = OrderBook.get_all_asks(ticker)
                last_price = OrderBook.get_last_price(ticker)
                last_timestamp = OrderBook.get_last_timestamp(ticker)
                pnl = PortfolioValue.calculate_pnl_24h(ticker)
                summary[ticker] = {
                    "ticker": ticker,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "all_bids": [
                        {
                            "order_id": to_public_order_id(order_id),
                            "timestamp": timestamp,
                            "price": price,
                            "volume": volume,
                            "stock_id": stock_id,
                        }
                        for order_id, timestamp, price, volume, stock_id in all_bids
                    ],
                    "all_asks": [
                        {
                            "order_id": to_public_order_id(order_id),
                            "timestamp": timestamp,
                            "price": price,
                            "volume": volume,
                            "stock_id": stock_id,
                        }
                        for order_id, timestamp, price, volume, stock_id in all_asks
                    ],
                    "last_price": last_price,
                    "last_timestamp": last_timestamp,
                    "server_time": server_time,
                    "pnl": pnl,
                }
            encoded = jsonable_encoder(summary)
            await websocket.send_text(json.dumps(encoded))
            await asyncio.sleep(1)  # Updates pushed every second
    except Exception as e:
        print(f"OrderBook WebSocket error: {e}")


async def _reject_client_info_subscription(websocket: WebSocket, message: str) -> None:
    await websocket.send_text(json.dumps({"error": message}))
    await websocket.close(code=1008)


async def client_info_websocket(websocket: WebSocket):
    """
    WebSocket endpoint to send client information (balance and portfolio).
    """
    await websocket.accept()
    try:
        subscription = ClientInfoWebSocketSubscription.model_validate_json(
            await websocket.receive_text()
        )
    except ValidationError:
        await _reject_client_info_subscription(
            websocket,
            "First message must be JSON with both email and token.",
        )
        return
    except WebSocketDisconnect:
        return
    except Exception as e:
        print(f"Client Info WebSocket error: {e}")
        await websocket.close(code=1011)
        return

    client = authenticate_client_info_token(subscription.email, subscription.token)
    if client is None:
        await _reject_client_info_subscription(
            websocket,
            "Invalid client_info subscription token.",
        )
        return

    print(f"Client subscribed for information: {client.email}")

    try:
        while True:
            pval = PortfolioValue.current_value(client)
            pnl = {}
            portfolioPnl = PortfolioValue.pnl_percent(client)
            for ticker in TICKERS:
                pnl[ticker] = PortfolioValue.calculate_pnl_24h(ticker)
            client_info = {
                "balance": client.balance,
                "portfolio": client.portfolio,
                "portfolioValue": pval,
                "pnlInfo": pnl,
                "portfolioPnl": portfolioPnl,
            }
            await websocket.send_text(json.dumps(client_info))
            await asyncio.sleep(1)  # Send updates every second
    except WebSocketDisconnect:
        return
    except Exception as e:
        print(f"Client Info WebSocket error: {e}")
        await websocket.close(code=1011)
        return


def register_websocket_routes(app: FastAPI) -> None:
    app.websocket("/ws")(websocket_endpoint)
    app.websocket("/client_info")(client_info_websocket)
