"""Database-backed publishing account catalog with environment-backed secrets."""

from __future__ import annotations

import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from .user_store import DB_PATH

_lock = threading.Lock()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS publishing_accounts (
                id              TEXT PRIMARY KEY,
                label           TEXT NOT NULL,
                secret_env_var  TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
            """
        )


def sync_environment_accounts(accounts: list[dict[str, str]]) -> None:
    """Persist account metadata; credential values themselves stay in the environment."""
    now = datetime.now(UTC).isoformat(timespec="seconds")
    with _lock, _connect() as conn:
        for account in accounts:
            account_id = account["id"]
            secret_env_var = (
                "DEV_TO_API_KEY"
                if account_id == "default"
                else f"DEV_TO_API_KEY_{account_id}"
            )
            conn.execute(
                """
                INSERT INTO publishing_accounts (id, label, secret_env_var, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    label = excluded.label,
                    secret_env_var = excluded.secret_env_var,
                    updated_at = excluded.updated_at
                """,
                (account_id, account["label"], secret_env_var, now, now),
            )


def list_accounts() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, label, secret_env_var FROM publishing_accounts ORDER BY id"
        ).fetchall()
    return [
        {
            "id": row["id"],
            "label": row["label"],
            "configured": bool(os.getenv(row["secret_env_var"])),
        }
        for row in rows
    ]


def get_account(account_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, label, secret_env_var FROM publishing_accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "label": row["label"],
        "configured": bool(os.getenv(row["secret_env_var"])),
    }
