from shopapp import orders
from shopapp.auth import require_auth, require_admin
from shopapp.db import fetch_all
from shopapp.errors import ValidationError
from shopapp.logging_utils import get_logger, redact

logger = get_logger("api")


def parse_int(value, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be an integer")


@require_auth
def get_order_handler(request: dict) -> dict:
    order = orders.get_order(parse_int(request.get("order_id"), "order_id"))
    if order["user_id"] != request["user"]["id"]:
        raise ValidationError("not your order")
    return {"order": order, "total": str(orders.order_total(order["id"]))}


@require_auth
def list_orders_handler(request: dict) -> dict:
    page = parse_int(request.get("page", 1), "page")
    return {"orders": orders.list_orders(request["user"]["id"], page)}


@require_admin
def list_users_handler(request: dict) -> dict:
    logger.info("admin listed users: %s", redact(request))
    return {"users": fetch_all("SELECT id, email FROM users")}
