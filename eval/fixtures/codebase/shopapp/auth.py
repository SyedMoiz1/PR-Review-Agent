import functools
import hashlib
import hmac
import secrets

from shopapp.db import fetch_one, execute
from shopapp.errors import AuthError
from shopapp.logging_utils import get_logger

logger = get_logger("auth")
PBKDF2_ITERATIONS = 310_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split("$", 1)
    candidate = hash_password(password, bytes.fromhex(salt_hex)).split("$", 1)[1]
    # constant-time comparison to avoid timing attacks
    return hmac.compare_digest(candidate, digest_hex)


def create_session_token(user_id: int) -> str:
    """Session tokens must come from the `secrets` module, never `random`."""
    token = secrets.token_urlsafe(32)
    execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))
    return token


def get_user_for_token(token: str) -> dict | None:
    return fetch_one(
        "SELECT users.* FROM users JOIN sessions ON sessions.user_id = users.id WHERE sessions.token = ?",
        (token,),
    )


def require_auth(handler):
    """Decorator for request handlers: resolves request['token'] to request['user'] or raises AuthError."""
    @functools.wraps(handler)
    def wrapper(request: dict, *args, **kwargs):
        user = get_user_for_token(request.get("token", ""))
        if user is None:
            raise AuthError("authentication required")
        request["user"] = user
        return handler(request, *args, **kwargs)
    return wrapper


def require_admin(handler):
    """Decorator for admin-only handlers. Implies require_auth."""
    @require_auth
    @functools.wraps(handler)
    def wrapper(request: dict, *args, **kwargs):
        if not request["user"].get("is_admin"):
            raise AuthError("admin required")
        return handler(request, *args, **kwargs)
    return wrapper
