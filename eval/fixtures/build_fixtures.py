# builds eval/fixtures/prs/*.json from the PR definitions below
#
# Each PR is written as "file content after the change" against eval/fixtures/codebase,
# and the patch is generated with difflib, so hunk line numbers are always correct.
# Ground-truth comments point at a line by a unique substring (`match`) which is resolved
# to the new-file line number here.
#
# usage: python -m eval.fixtures.build_fixtures
import difflib
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from github_parsing.diff_parser import parse_patch

HERE = Path(__file__).parent
CODEBASE = HERE / "codebase"
OUT_DIR = HERE / "prs"


def base(path: str) -> str:
    return (CODEBASE / path).read_text()


def append(path: str, code: str) -> str:
    return base(path).rstrip("\n") + "\n\n\n" + code.strip("\n") + "\n"


def make_patch(before: str, after: str) -> str:
    diff = difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=3)
    return "\n".join(list(diff)[2:])  # drop the ---/+++ header lines, like GitHub's file.patch


PRS = [
    {
        "id": "01-sql-injection",
        "title": "Add order search by status",
        "files": {"shopapp/orders.py": append("shopapp/orders.py", '''
def search_orders(user_id: int, status: str) -> list[dict]:
    return fetch_all(f"SELECT * FROM orders WHERE user_id = {user_id} AND status = '{status}'")
''')},
        "expected": [("shopapp/orders.py", 'f"SELECT * FROM orders WHERE user_id = {user_id}', "critical",
                      "SQL injection: values are interpolated into the query with an f-string. fetch_all takes a params tuple; use placeholders like the rest of orders.py.")],
    },
    {
        "id": "02-timing-unsafe-compare",
        "title": "Add API key check for webhooks",
        "files": {"shopapp/auth.py": append("shopapp/auth.py", '''
def verify_api_key(provided: str, expected: str) -> bool:
    return provided == expected
''')},
        "expected": [("shopapp/auth.py", "return provided == expected", "major",
                      "Secret comparison with == leaks timing information. verify_password uses hmac.compare_digest; do the same here.")],
    },
    {
        "id": "03-float-money",
        "title": "Add shipping cost calculation",
        "files": {"shopapp/shipping.py": '''from shopapp.money import to_money


def shipping_cost(weight_kg: float, rate_per_kg: float = 4.99) -> float:
    cost = weight_kg * rate_per_kg
    return round(cost, 2)
'''},
        "expected": [("shopapp/shipping.py", "return round(cost, 2)", "major",
                      "Money is computed with float and round(). The codebase requires Decimal via money.to_money (rounded half-up); float arithmetic gives wrong cents.")],
    },
    {
        "id": "04-missing-admin-auth",
        "title": "Add endpoint to delete a user",
        "files": {"shopapp/api.py": append("shopapp/api.py", '''
def delete_user_handler(request: dict) -> dict:
    user_id = parse_int(request.get("user_id"), "user_id")
    execute("DELETE FROM users WHERE id = ?", (user_id,))
    return {"deleted": user_id}
''').replace("from shopapp.db import fetch_all", "from shopapp.db import fetch_all, execute")},
        "expected": [("shopapp/api.py", "def delete_user_handler", "critical",
                      "Destructive admin endpoint has no authorization. Other admin handlers are wrapped with @require_admin; anyone can delete users here.")],
    },
    {
        "id": "05-raw-connection",
        "title": "Add product stock lookup",
        "files": {"shopapp/inventory.py": '''import sqlite3

from shopapp.config import DATABASE_PATH


def stock_level(product_id: int) -> int:
    conn = sqlite3.connect(DATABASE_PATH)
    row = conn.execute("SELECT stock FROM products WHERE id = ?", (product_id,)).fetchone()
    return row[0]
'''},
        "expected": [
            ("shopapp/inventory.py", "conn = sqlite3.connect(DATABASE_PATH)", "major",
             "Opens a raw sqlite3 connection that is never closed. db.py requires using get_connection()/fetch_one, which commit, roll back and close."),
            ("shopapp/inventory.py", "return row[0]", "minor",
             "row is None for an unknown product_id, so this raises TypeError. Raise NotFoundError like orders.get_order."),
        ],
    },
    {
        "id": "06-bare-except",
        "title": "Make order total resilient",
        "files": {"shopapp/orders.py": base("shopapp/orders.py").replace(
            '''def order_total(order_id: int) -> Decimal:
    items = fetch_all("SELECT price, quantity FROM order_items WHERE order_id = ?", (order_id,))
    return to_money(sum(to_money(i["price"]) * i["quantity"] for i in items))''',
            '''def order_total(order_id: int) -> Decimal:
    try:
        items = fetch_all("SELECT price, quantity FROM order_items WHERE order_id = ?", (order_id,))
        return to_money(sum(to_money(i["price"]) * i["quantity"] for i in items))
    except:
        return to_money(0)''')},
        "expected": [("shopapp/orders.py", "    except:", "major",
                      "Bare except swallows every error (including DB failures) and reports a $0.00 total. Let errors propagate or catch a specific exception and log via logger.")],
    },
    {
        "id": "07-mutable-default",
        "title": "Add cart helper",
        "files": {"shopapp/cart.py": '''from shopapp.money import to_money


def add_to_cart(item: dict, cart: list = []) -> list:
    cart.append({"price": to_money(item["price"]), "quantity": item["quantity"]})
    return cart
'''},
        "expected": [("shopapp/cart.py", "def add_to_cart(item: dict, cart: list = []) -> list:", "major",
                      "Mutable default argument: the same list is shared across calls, so carts leak between users. Default to None and create a new list.")],
    },
    {
        "id": "08-pagination-off-by-one",
        "title": "Add pagination to admin order list",
        "files": {"shopapp/admin.py": '''from shopapp.config import PAGE_SIZE
from shopapp.db import fetch_all


def list_all_orders(page: int = 1) -> list[dict]:
    offset = page * PAGE_SIZE
    return fetch_all("SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?", (PAGE_SIZE, offset))
'''},
        "expected": [("shopapp/admin.py", "offset = page * PAGE_SIZE", "major",
                      "Off-by-one: pages are 1-based (see orders.list_orders), so page 1 skips the first PAGE_SIZE orders. Use (page - 1) * PAGE_SIZE and validate page >= 1.")],
    },
    {
        "id": "09-logs-password",
        "title": "Log login attempts",
        "files": {"shopapp/auth.py": append("shopapp/auth.py", '''
def login(request: dict) -> str:
    logger.info("login attempt: %s", request)
    user = fetch_one("SELECT * FROM users WHERE email = ?", (request["email"],))
    if user is None or not verify_password(request["password"], user["password_hash"]):
        raise AuthError("invalid credentials")
    return create_session_token(user["id"])
''')},
        "expected": [("shopapp/auth.py", 'logger.info("login attempt: %s", request)', "critical",
                      "Logs the raw request, including the plaintext password. Use logging_utils.redact(request) as api.py does.")],
    },
    {
        "id": "10-http-no-timeout",
        "title": "Fetch exchange rates",
        "files": {"shopapp/rates.py": '''import json
import urllib.request


def usd_to_eur() -> float:
    with urllib.request.urlopen("https://api.example.com/rates/usd") as resp:
        return json.loads(resp.read())["eur"]
'''},
        "expected": [("shopapp/rates.py", "urllib.request.urlopen(", "major",
                      "Outbound HTTP call without a timeout or retries can hang the worker. Use http_client.get_json, which applies HTTP_TIMEOUT_SECONDS and backoff.")],
    },
    {
        "id": "11-division-by-zero",
        "title": "Add average order value report",
        "files": {"shopapp/reports.py": '''from decimal import Decimal

from shopapp.db import fetch_all
from shopapp.money import to_money
from shopapp.orders import order_total


def average_order_value(user_id: int) -> Decimal:
    orders = fetch_all("SELECT id FROM orders WHERE user_id = ?", (user_id,))
    total = sum(order_total(o["id"]) for o in orders)
    return to_money(total / len(orders))
'''},
        "expected": [
            ("shopapp/reports.py", "return to_money(total / len(orders))", "major",
             "ZeroDivisionError for users with no orders. Return to_money(0) (or raise ValidationError) when orders is empty."),
            ("shopapp/reports.py", "total = sum(order_total(", "minor",
             "N+1 queries: order_total runs one query per order. Compute totals in one query or batch-load with items_for_orders."),
        ],
    },
    {
        "id": "12-hardcoded-secret",
        "title": "Sign password reset links",
        "files": {"shopapp/reset.py": '''import hashlib
import hmac

RESET_SECRET = "s3cr3t-reset-key-2024"


def reset_signature(user_id: int) -> str:
    return hmac.new(RESET_SECRET.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()
'''},
        "expected": [("shopapp/reset.py", 'RESET_SECRET = "s3cr3t-reset-key-2024"', "critical",
                      "Hardcoded secret committed to source. config.py loads secrets from the environment (SECRET_KEY); use that.")],
    },
    {
        "id": "13-n-plus-one",
        "title": "Show items on order history page",
        "files": {"shopapp/history.py": '''from shopapp.db import fetch_all
from shopapp.orders import list_orders


def order_history(user_id: int, page: int = 1) -> list[dict]:
    history = []
    for order in list_orders(user_id, page):
        items = fetch_all("SELECT * FROM order_items WHERE order_id = ?", (order["id"],))
        history.append({**order, "items": items})
    return history
'''},
        "expected": [("shopapp/history.py", 'items = fetch_all("SELECT * FROM order_items WHERE order_id = ?"', "major",
                      "N+1 query: one query per order on the page. orders.items_for_orders batch-loads items for many orders in a single query.")],
    },
    {
        "id": "14-clean-change",
        "title": "Add helper to cancel an order",
        "files": {"shopapp/orders.py": append("shopapp/orders.py", '''
def cancel_order(order_id: int, user_id: int) -> None:
    order = get_order(order_id)
    if order["user_id"] != user_id:
        raise ValidationError("not your order")
    execute("UPDATE orders SET status = ? WHERE id = ?", ("cancelled", order_id))
    logger.info("cancelled order %s for user %s", order_id, user_id)
''')},
        "expected": [],  # correct change that follows codebase patterns: any comment is a false positive
    },
    {
        "id": "15-insecure-token",
        "title": "Add email verification tokens",
        "files": {"shopapp/verification.py": '''import random
import string

from shopapp.db import execute


def create_verification_token(user_id: int) -> str:
    token = "".join(random.choice(string.ascii_letters) for _ in range(16))
    print(f"created verification token {token} for {user_id}")
    execute("INSERT INTO verification_tokens (token, user_id) VALUES (?, ?)", (token, user_id))
    return token
'''},
        "expected": [
            ("shopapp/verification.py", "token = \"\".join(random.choice(", "critical",
             "Security token generated with the non-cryptographic `random` module, so it is predictable. Use secrets.token_urlsafe like auth.create_session_token."),
            ("shopapp/verification.py", 'print(f"created verification token', "minor",
             "print() leaks the token to stdout. Use get_logger and don't log the token value."),
        ],
    },
]


def build() -> list[dict]:
    OUT_DIR.mkdir(exist_ok=True)
    fixtures = []
    for pr in PRS:
        files = []
        diff_lines = []
        for path, after in pr["files"].items():
            before = base(path) if (CODEBASE / path).exists() else ""
            patch = make_patch(before, after)
            files.append({"filename": path, "patch": patch})
            diff_lines.extend(parse_patch(path, patch))

        expected = []
        for path, match, severity, comment in pr["expected"]:
            hits = [l for l in diff_lines if l["filename"] == path and l["change_type"] == "added" and match in l["content"]]
            if len(hits) != 1:
                raise ValueError(f"{pr['id']}: match {match!r} hit {len(hits)} added lines (need exactly 1)")
            expected.append({"file_path": path, "line_number": hits[0]["line_number"], "severity": severity, "comment": comment})

        fixture = {"id": pr["id"], "title": pr["title"], "files": files, "expected": expected}
        (OUT_DIR / f"{pr['id']}.json").write_text(json.dumps(fixture, indent=2) + "\n")
        fixtures.append(fixture)
    return fixtures


if __name__ == "__main__":
    print(f"Wrote {len(build())} fixtures to {OUT_DIR}")
