from decimal import Decimal

from shopapp.config import PAGE_SIZE
from shopapp.db import fetch_all, fetch_one, execute
from shopapp.errors import NotFoundError, ValidationError
from shopapp.money import to_money
from shopapp.logging_utils import get_logger

logger = get_logger("orders")


def get_order(order_id: int) -> dict:
    order = fetch_one("SELECT * FROM orders WHERE id = ?", (order_id,))
    if order is None:
        raise NotFoundError(f"order {order_id} not found")
    return order


def order_total(order_id: int) -> Decimal:
    items = fetch_all("SELECT price, quantity FROM order_items WHERE order_id = ?", (order_id,))
    return to_money(sum(to_money(i["price"]) * i["quantity"] for i in items))


def list_orders(user_id: int, page: int = 1) -> list[dict]:
    """Pages are 1-based."""
    if page < 1:
        raise ValidationError("page must be >= 1")
    offset = (page - 1) * PAGE_SIZE
    return fetch_all(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (user_id, PAGE_SIZE, offset),
    )


def items_for_orders(order_ids: list[int]) -> dict[int, list[dict]]:
    """Batch-load items for many orders in one query (avoid N+1 queries)."""
    if not order_ids:
        return {}
    placeholders = ",".join("?" for _ in order_ids)
    rows = fetch_all(f"SELECT * FROM order_items WHERE order_id IN ({placeholders})", tuple(order_ids))
    grouped: dict[int, list[dict]] = {oid: [] for oid in order_ids}
    for row in rows:
        grouped[row["order_id"]].append(row)
    return grouped


def create_order(user_id: int, items: list[dict]) -> int:
    if not items:
        raise ValidationError("order must contain at least one item")
    order_id = execute("INSERT INTO orders (user_id) VALUES (?)", (user_id,))
    for item in items:
        if item["quantity"] <= 0:
            raise ValidationError("quantity must be positive")
        execute(
            "INSERT INTO order_items (order_id, price, quantity) VALUES (?, ?, ?)",
            (order_id, str(to_money(item["price"])), item["quantity"]),
        )
    logger.info("created order %s for user %s", order_id, user_id)
    return order_id
