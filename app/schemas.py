from pydantic import BaseModel


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


class PublicTransaction(BaseModel):
    ticker: str
    price: float
    volume: int
    timestamp: str
