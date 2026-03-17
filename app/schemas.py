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
    order_id: int


class EditOrderRequest(BaseModel):
    order_id: int
    price: float
    volume: int


class ClientData(BaseModel):
    email: str
    first_name: str
    last_name: str
