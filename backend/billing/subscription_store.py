from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from backend.billing.constants import CUSTOMER_ID_PATTERN, USER_ID_PATTERN

logger = logging.getLogger(__name__)

DB_PATH = Path("./data/subscriptions.db")

VALID_TIERS = {"free", "pro", "team"}
VALID_STATUSES = {"active", "cancelled", "past_due", "trialing", "unpaid"}

SUBSCRIPTION_ID_PATTERN = re.compile(r"^sub_[a-zA-Z0-9]{14,}$")


def init_db() -> None:
    """Create subscriptions table if not exists."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id      TEXT PRIMARY KEY,
                customer_id  TEXT UNIQUE,
                tier         TEXT NOT NULL DEFAULT 'free',
                status       TEXT NOT NULL DEFAULT 'active',
                updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Context manager for SQLite connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class SubscriptionStore:
    """
    Server-side subscription tier storage.
    Tier is ONLY read from this DB — never from client headers or JWTs.
    """

    def __init__(self) -> None:
        init_db()

    def upsert(
        self,
        user_id: str,
        customer_id: str,
        tier: str,
        status: str,
    ) -> None:
        """Insert or update subscription record."""
        if tier not in VALID_TIERS:
            raise ValueError(f"Invalid tier: {tier!r}")
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status!r}")
        if not USER_ID_PATTERN.fullmatch(user_id):
            raise ValueError("Invalid user_id format")
        if not CUSTOMER_ID_PATTERN.fullmatch(customer_id):
            raise ValueError(f"Invalid customer_id format: {customer_id!r}")

        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO subscriptions (user_id, customer_id, tier, status, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    customer_id = excluded.customer_id,
                    tier        = excluded.tier,
                    status      = excluded.status,
                    updated_at  = datetime('now')
                """,
                (user_id, customer_id, tier, status),
            )

    def get_tier(self, user_id: str) -> str:
        """
        Return subscription tier for user.
        Returns "free" if user not found.
        Raises RuntimeError if DB unavailable — caller should fail closed.
        """
        try:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT tier, status FROM subscriptions WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
            if not row:
                return "free"
            if row["status"] in ("cancelled", "past_due", "unpaid"):
                return "free"
            return str(row["tier"])
        except sqlite3.Error as exc:
            raise RuntimeError(f"Subscription DB unavailable: {exc}") from exc

    def get_by_customer_id(self, customer_id: str) -> dict | None:
        """Look up subscription by Stripe customer_id."""
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM subscriptions WHERE customer_id = ?",
                (customer_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_by_user_id(self, user_id: str) -> dict | None:
        """Look up subscription by user_id."""
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM subscriptions WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None
