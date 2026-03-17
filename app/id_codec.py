import uuid

from fastapi import HTTPException

from models.order import Order


ORDER_ID_NAMESPACE = uuid.UUID("4f3e6867-0a48-4ef9-a54f-4f315fdb9b29")
CLIENT_ID_NAMESPACE = uuid.UUID("d1e8f3f0-fd46-4a4d-95eb-1dfb0f6bc0f2")


def to_public_order_id(order_id: int) -> str:
    return str(uuid.uuid5(ORDER_ID_NAMESPACE, f"order:{order_id}"))


def to_internal_order_id(order_id: str | int) -> int:
    if isinstance(order_id, int):
        return order_id

    try:
        target = uuid.UUID(order_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid order id format. Must be a UUID string.",
        ) from exc

    for internal_id, order in Order._all_orders.items():
        if uuid.uuid5(ORDER_ID_NAMESPACE, f"order:{internal_id}") == target:
            return internal_id

    raise HTTPException(status_code=404, detail=f"Order {order_id} does not exist.")


def to_public_client_id(client_id: int) -> str:
    return str(uuid.uuid5(CLIENT_ID_NAMESPACE, f"client:{client_id}"))
