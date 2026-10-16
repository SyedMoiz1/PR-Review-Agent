import sqlite3
from contextlib import contextmanager

from shopapp.config import DATABASE_PATH


@contextmanager
def get_connection():
    """Yield a connection that is committed on success, rolled back on error and always closed.

    Every module must use this instead of calling sqlite3.connect directly.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_one(query: str, params: tuple = ()) -> dict | None:
    """Run a parameterized query and return the first row. Never format values into `query`."""
    with get_connection() as conn:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None


def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    """Run a parameterized query and return all rows. Never format values into `query`."""
    with get_connection() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def execute(query: str, params: tuple = ()) -> int:
    """Run a parameterized write and return the last row id."""
    with get_connection() as conn:
        cursor = conn.execute(query, params)
        return cursor.lastrowid
