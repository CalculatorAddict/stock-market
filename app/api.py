from fastapi import FastAPI, Header, HTTPException

from OrderBook.OrderBook import *
from OrderBook.tickers import *
from database import Database
import new_user_portfolio as new_user

from app.schemas import (
    BestBidAskResponse,
    BestPriceResponse,
    CancelOrderResponse,
    CancelOrderRequest,
    ClientData,
    EditOrderRequest,
    EditOrderResponse,
    MarketOrderRequest,
    OrderBookLevel,
    OrderIdResponse,
    OrderStatusResponse,
    PlaceOrderRequest,
    PublicClientResponse,
    PublicTransaction,
    VolumeAtPriceResponse,
)
from app.id_codec import to_internal_order_id, to_public_client_id, to_public_order_id
from app.shared_constants import IDENTITY_HEADER_EMAIL, IDENTITY_HEADER_USER
from app.validation import orderbook_error_to_http, validate_side, validate_ticker


def _serialize_public_client(client: Client) -> dict:
    return {
        "client_id": to_public_client_id(client.client_id),
        "username": client.username,
        "email": client.email,
        "first_name": client.first_names,
        "last_name": client.last_name,
        "balance": client.balance,
        "portfolio": client.portfolio,
    }


def _normalize_identity(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized if normalized else None


def _assert_actor_headers_present(
    actor_user: str | None, actor_email: str | None
) -> None:
    if (
        _normalize_identity(actor_user) is None
        and _normalize_identity(actor_email) is None
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Missing identity headers. "
                f"Provide {IDENTITY_HEADER_USER} or {IDENTITY_HEADER_EMAIL}."
            ),
        )


def _assert_actor_matches_client(
    client: Client, actor_user: str | None, actor_email: str | None
) -> None:
    _assert_actor_headers_present(actor_user, actor_email)

    normalized_user = _normalize_identity(actor_user)
    normalized_email = _normalize_identity(actor_email)

    if normalized_user is not None and normalized_user != client.username.lower():
        raise HTTPException(
            status_code=403, detail="Actor username does not match target user."
        )

    if normalized_email is not None and normalized_email != client.email.lower():
        raise HTTPException(
            status_code=403, detail="Actor email does not match target user."
        )


def _assert_actor_matches_email(request_email: str, actor_email: str | None) -> None:
    normalized_actor_email = _normalize_identity(actor_email)
    if normalized_actor_email is None:
        raise HTTPException(
            status_code=401,
            detail=f"Missing identity header {IDENTITY_HEADER_EMAIL}.",
        )

    if normalized_actor_email != request_email.strip().lower():
        raise HTTPException(
            status_code=403, detail="Actor email does not match target user."
        )


async def place_order(
    order: PlaceOrderRequest,
    x_actor_user: str | None = Header(default=None, alias=IDENTITY_HEADER_USER),
    x_actor_email: str | None = Header(default=None, alias=IDENTITY_HEADER_EMAIL),
):
    """
    Place a limit order for a stock.

    Parameters:
    - ticker: The ticker of the order book.
    - side: The side of the order (buy/sell).
    - price: The price at which to place the order.
    - volume: The number of shares to order.
    - client_user: The username of the client placing the order.

    Returns:
    - order_id if successful, or an error message.
    """
    ticker = order.ticker
    side = order.side
    price = order.price
    volume = order.volume
    client = Client.get_client_by_username(order.client_user)

    if client is None:
        raise HTTPException(
            status_code=404,
            detail=f"Client with username {order.client_user} not found.",
        )
    _assert_actor_matches_client(client, x_actor_user, x_actor_email)

    ticker = validate_ticker(ticker)
    side = validate_side(side)

    if price <= 0:
        raise HTTPException(
            status_code=400, detail="Limit order price must be greater than zero."
        )
    if volume <= 0:
        raise HTTPException(
            status_code=400, detail="Limit order volume must be greater than zero."
        )

    print(f"Placing order for stock {ticker}: {side} at {price} for {volume} shares")
    order_side = BUY if side.lower() == "buy" else SELL
    try:
        order_id = OrderBook.place_order(ticker, order_side, price, volume, client)
        return to_public_order_id(order_id)
    except Exception as e:
        orderbook_error_to_http(e)


async def market_order(
    order: MarketOrderRequest,
    x_actor_user: str | None = Header(default=None, alias=IDENTITY_HEADER_USER),
    x_actor_email: str | None = Header(default=None, alias=IDENTITY_HEADER_EMAIL),
):
    """
    Place a market order for a stock.

    Parameters:
    - ticker: The ticker of the order book.
    - side: The side of the order (buy/sell).
    - volume: The number of shares to order.
    - client_user: The username of the client placing the order.

    Returns:
    - order_id if successful, or an error message.
    """
    ticker = order.ticker
    side = order.side
    volume = order.volume
    client = Client.get_client_by_username(order.client_user)

    if client is None:
        raise HTTPException(
            status_code=404,
            detail=f"Client with username {order.client_user} not found.",
        )
    _assert_actor_matches_client(client, x_actor_user, x_actor_email)

    ticker = validate_ticker(ticker)
    side = validate_side(side)

    if volume <= 0:
        raise HTTPException(
            status_code=400, detail="Market order volume must be greater than zero."
        )

    print(
        f"Placing order for stock {ticker}: {side} at market price for {volume} shares"
    )
    order_side = BUY if side.lower() == "buy" else SELL
    try:
        order_id = OrderBook.market_order(ticker, order_side, volume, client)
        return to_public_order_id(order_id)
    except Exception as e:
        orderbook_error_to_http(e)


async def cancel_order(
    request: CancelOrderRequest,
    x_actor_user: str | None = Header(default=None, alias=IDENTITY_HEADER_USER),
    x_actor_email: str | None = Header(default=None, alias=IDENTITY_HEADER_EMAIL),
):
    """
    Cancel an order for a stock.

    Parameters:
    - order_id: The ID of the order to cancel.

    Returns:
    - success message if successful, or an error message.
    """

    order_id = to_internal_order_id(request.order_id)
    if order_id < 0:
        raise HTTPException(status_code=400, detail="Order id must be non-negative.")

    order = Order.get_order_by_id(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} does not exist.")
    _assert_actor_matches_client(order.client, x_actor_user, x_actor_email)

    print(f"Cancelling order {order_id}")
    try:
        response = OrderBook.cancel_order(order_id)
    except Exception as e:
        orderbook_error_to_http(e)

    return {
        "status": "success",
        "order_id": to_public_order_id(order_id),
        "message": response,
    }


async def edit_order(
    request: EditOrderRequest,
    x_actor_user: str | None = Header(default=None, alias=IDENTITY_HEADER_USER),
    x_actor_email: str | None = Header(default=None, alias=IDENTITY_HEADER_EMAIL),
):
    """
    Edit an existing order for a stock.

    Parameters:
    - order_id: The ID of the order to edit.
    - price: The new price for the order.
    - volume: The new volume for the order.

    Returns:
    - success message if successful, or an error message.
    """
    order_id = to_internal_order_id(request.order_id)
    if order_id < 0:
        raise HTTPException(status_code=400, detail="Order id must be non-negative.")

    price = request.price
    volume = request.volume
    if price <= 0:
        raise HTTPException(
            status_code=400, detail="Order price must be greater than zero."
        )
    if volume <= 0:
        raise HTTPException(
            status_code=400, detail="Order volume must be greater than zero."
        )

    order = Order.get_order_by_id(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} does not exist.")
    _assert_actor_matches_client(order.client, x_actor_user, x_actor_email)

    print(f"Editing order {order_id}: new price {price}, new volume {volume}")
    try:
        diff, message = OrderBook.edit_order(order_id, price, volume)
    except Exception as e:
        orderbook_error_to_http(e)

    return {
        "status": "success",
        "order_id": to_public_order_id(order_id),
        "message": message,
        "delta_volume": diff,
    }


async def get_best_bid(ticker: str):
    """
    Get the best bid for a stock.

    Parameters:
    - ticker: The ticker of the order book.

    Returns:
    - best bid price if successful, or an error message.
    """

    print(f"Getting best bid for stock {ticker}")
    ticker = validate_ticker(ticker)
    return OrderBook.get_best_bid(ticker)


async def get_best_ask(ticker: str):
    """
    Get the best ask for a stock.

    Parameters:
    - ticker: The ticker of the order book.

    Returns:
    - best ask price if successful, or an error message.
    """

    print(f"Getting best ask for stock {ticker}")
    ticker = validate_ticker(ticker)
    return OrderBook.get_best_ask(ticker)


async def get_best(ticker: str):
    """
    Get the best bid and ask for a stock.

    Parameters:
    - ticker: The ticker of the order book.

    Returns:
    - best bid and ask prices if successful, or an error message.
    """

    print(f"Getting best bid and ask for stock {ticker}")
    ticker = validate_ticker(ticker)
    best_bid, best_ask = OrderBook.get_best(ticker)
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
    }


async def get_volume_at_price(ticker: str, side: str, price: float):
    """
    Get the volume at a specific price for a stock.

    Parameters:
    - ticker: The ticker of the order book.
    - price: The price at which to get the volume.

    Returns:
    - volume at the specified price if successful, or an error message.
    """

    print(f"Getting volume at price {price} for stock {ticker}")
    ticker = validate_ticker(ticker)
    side = validate_side(side)
    order_side = BUY if side == BUY.value else SELL
    return OrderBook.get_volume_at_price(ticker, order_side, price)


async def get_all_asks(ticker: str):
    """
    Get all ask orders for a stock.

    Parameters:
    - ticker: The ticker of the order book.

    Returns:
    - list of all ask orders if successful, or an error message.
    """

    print(f"Getting all asks for stock {ticker}")
    ticker = validate_ticker(ticker)
    all_asks = OrderBook.get_all_asks(ticker)
    print(all_asks)
    return [
        {
            "order_id": to_public_order_id(order_id),
            "timestamp": timestamp,
            "price": price,
            "volume": volume,
            "stock_id": stock_id,
        }
        for order_id, timestamp, price, volume, stock_id in all_asks
    ]


async def get_all_bids(ticker: str):
    """
    Get all bid orders for a stock.

    Parameters:
    - ticker: The ticker of the order book.

    Returns:
    - list of all bid orders if successful, or an error message.
    """

    print(f"Getting all bids for stock {ticker}")
    ticker = validate_ticker(ticker)
    all_bids = OrderBook.get_all_bids(ticker)
    print(all_bids)
    return [
        {
            "order_id": to_public_order_id(order_id),
            "timestamp": timestamp,
            "price": price,
            "volume": volume,
            "stock_id": stock_id,
        }
        for order_id, timestamp, price, volume, stock_id in all_bids
    ]


async def get_transactions(ticker: str, limit: int = 20):
    """
    Get recent transactions for a stock.

    Parameters:
    - ticker: The ticker to query.
    - limit: Maximum number of transactions to return (most recent first). Defaults to 20.

    Returns an anonymized transaction stream with only public fields.
    """
    if limit <= 0:
        raise HTTPException(
            status_code=400,
            detail="Limit must be a positive integer.",
        )

    ticker = validate_ticker(ticker)
    rows = Database().retrieve_transactions_stock(ticker)
    rows = sorted(rows, key=lambda row: row[0], reverse=True)[:limit]

    transactions = []
    for (
        _transaction_id,
        _bidder_id,
        _bid_price,
        _asker_id,
        _ask_price,
        volume,
        ticker_value,
        _timestamp,
        transaction_price,
    ) in rows:
        transactions.append(
            {
                "ticker": ticker_value,
                "price": transaction_price,
                "volume": volume,
                "timestamp": _timestamp,
            }
        )

    return transactions


async def get_order_status(
    order_id: str | int,
    x_actor_user: str | None = Header(default=None, alias=IDENTITY_HEADER_USER),
    x_actor_email: str | None = Header(default=None, alias=IDENTITY_HEADER_EMAIL),
):
    internal_order_id = to_internal_order_id(order_id)
    if internal_order_id < 0:
        raise HTTPException(status_code=400, detail="Order id must be non-negative.")

    order = Order.get_order_by_id(internal_order_id)
    if order is None:
        raise HTTPException(
            status_code=404, detail=f"Order {internal_order_id} does not exist."
        )
    _assert_actor_matches_client(order.client, x_actor_user, x_actor_email)

    executed_volume = order.get_executed_volume()
    remaining_volume = order.get_volume()
    total_volume = order.get_total_volume()

    if order.terminated:
        status = "filled" if remaining_volume == 0 else "canceled"
    else:
        status = "partially_filled" if executed_volume > 0 else "open"

    return {
        "order_id": to_public_order_id(internal_order_id),
        "ticker": order.ticker,
        "side": order.side.value,
        "order_type": order.type.value,
        "price": order.price,
        "total_volume": total_volume,
        "executed_volume": executed_volume,
        "remaining_volume": remaining_volume,
        "terminated": order.terminated,
        "status": status,
    }


async def get_client_by_email(
    email: str,
    x_actor_email: str | None = Header(default=None, alias=IDENTITY_HEADER_EMAIL),
):
    """
    Used to get a client from the backend by its email.

    Parameters:
    - email: The email we are looking for.

    Returns:
    - The object of the client if it exists or None otherwise.
    """

    _assert_actor_matches_email(email, x_actor_email)
    print(f"Getting information for client with email {email}")
    client = Client.get_client_by_email(email)
    if client is None:
        raise HTTPException(
            status_code=404, detail=f"Client with email {email} not found."
        )
    return _serialize_public_client(client)


# need to add a proper username and a proper password.
# need to add stock for every ticker !!!!
async def add_new_client(
    client_data: ClientData,
    x_actor_email: str | None = Header(default=None, alias=IDENTITY_HEADER_EMAIL),
):
    """
    Used to get information of a client based on its email. If it doesn not exist, create a new client

    Parameters:
    - email, first name and last name

    Returns:
    - The object of the client
    """
    _assert_actor_matches_email(client_data.email, x_actor_email)
    queryClient = Client.get_client_by_email(client_data.email)

    if queryClient != None:
        return _serialize_public_client(queryClient)
    else:
        if Database().is_email_taken(client_data.email):
            details = Database().account_from_email(client_data.email)
            stocks = Database().retrieve_stock(details[0])
            dic = {}
            for stock in stocks:
                dic[stock[0]] = stock[2]
            client = Client(
                details[1],
                "pass",
                client_data.email,
                client_data.first_name,
                client_data.last_name,
                Database().retrieve_balance(details[0]),
                dic,
            )
        else:
            client = Client(
                client_data.email,
                "pass",
                client_data.email,
                client_data.first_name,
                client_data.last_name,
                new_user.money,
                {stock: volume for stock, volume in new_user.stocks.items()},
            )
            id = Database().create_client(
                client_data.email,
                client_data.email,
                new_user.money,
                client_data.first_name,
                client_data.last_name,
            )
            for stock, volume in new_user.stocks.items():
                Database().create_owned_stock(id, stock, volume)
        return _serialize_public_client(client)


def register_api_routes(app: FastAPI) -> None:
    app.post("/api/place_order", response_model=OrderIdResponse)(place_order)
    app.post("/api/market_order", response_model=OrderIdResponse)(market_order)
    app.post("/api/cancel_order", response_model=CancelOrderResponse)(cancel_order)
    app.post("/api/edit_order", response_model=EditOrderResponse)(edit_order)
    app.get("/api/get_best_bid", response_model=BestPriceResponse)(get_best_bid)
    app.get("/api/get_best_ask", response_model=BestPriceResponse)(get_best_ask)
    app.get("/api/get_best", response_model=BestBidAskResponse)(get_best)
    app.get("/api/get_volume_at_price", response_model=VolumeAtPriceResponse)(
        get_volume_at_price
    )
    app.get("/api/get_all_asks", response_model=list[OrderBookLevel])(get_all_asks)
    app.get("/api/get_all_bids", response_model=list[OrderBookLevel])(get_all_bids)
    app.get("/api/order_status", response_model=OrderStatusResponse)(get_order_status)
    app.get("/api/transactions", response_model=list[PublicTransaction])(
        get_transactions
    )
    app.get("/api/get_client_by_email", response_model=PublicClientResponse)(
        get_client_by_email
    )
    app.post("/api/add_new_client", response_model=PublicClientResponse)(add_new_client)
