from datetime import datetime

from pydantic import BaseModel, RootModel


class PlaceOrderRequest(BaseModel):
    ticker: str
    side: str
    price: float
    volume: int
    client_user: str


class MarketOrderRequest(BaseModel):
    ticker: str
    side: str
    volume: int
    client_user: str


class OrderIdResponse(RootModel[str]):
    pass


class CancelOrderRequest(BaseModel):
    order_id: str | int


class EditOrderRequest(BaseModel):
    order_id: str | int
    price: float
    volume: int


class ClientData(BaseModel):
    email: str
    first_name: str
    last_name: str


class PublicClientResponse(BaseModel):
    client_id: str
    username: str
    email: str
    first_name: str
    last_name: str
    balance: float
    portfolio: dict[str, float]


class DemoAccount(BaseModel):
    username: str
    email: str


class DemoResponse(BaseModel):
    title: str
    description: str
    default_ticker: str
    accounts: list[DemoAccount]


class CancelOrderResponse(BaseModel):
    status: str
    order_id: str
    message: str


class EditOrderResponse(BaseModel):
    status: str
    order_id: str
    message: str
    delta_volume: int


class OrderBookLevel(BaseModel):
    order_id: str
    timestamp: datetime
    price: float
    volume: int
    stock_id: int


class BestPriceResponse(RootModel[float | None]):
    pass


class VolumeAtPriceResponse(RootModel[int]):
    pass


class BestBidAskResponse(BaseModel):
    best_bid: float | None
    best_ask: float | None


class PublicTransaction(BaseModel):
    ticker: str
    price: float
    volume: int
    timestamp: str


class OrderStatusResponse(BaseModel):
    order_id: str
    ticker: str
    side: str
    order_type: str
    price: float
    total_volume: int
    executed_volume: int
    remaining_volume: int
    terminated: bool
    status: str
