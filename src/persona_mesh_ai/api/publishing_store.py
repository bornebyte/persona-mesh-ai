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
        account_rows = conn.execute(
            "SELECT id, label, secret_env_var FROM publishing_accounts ORDER BY id"
        ).fetchall()
        user_rows = conn.execute(
            """
            SELECT persona_id, name, role, description, relationship, personality
            FROM users
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()

    accounts_by_id = {row["id"]: row for row in account_rows}
    user_accounts: list[dict[str, Any]] = []
    for user in user_rows:
        account_id = user["persona_id"]
        if not account_id:
            continue
        account_row = accounts_by_id.pop(account_id, None)
        secret_env_var = (
            account_row["secret_env_var"]
            if account_row is not None
            else f"DEV_TO_API_KEY_{account_id}"
        )
        user_accounts.append(
            {
                "id": account_id,
                "label": user["name"],
                "name": user["name"],
                "role": user["role"],
                "description": user["description"],
                "relationship": user["relationship"],
                "personality": user["personality"],
                "source": "user",
                "configured": bool(os.getenv(secret_env_var)),
            }
        )

    other_accounts = [
        {
            "id": row["id"],
            "label": row["label"],
            "name": row["label"],
            "role": "Dev.to publishing account",
            "description": "Connected publishing account.",
            "relationship": "",
            "personality": "",
            "source": "publishing_account",
            "configured": bool(os.getenv(row["secret_env_var"])),
        }
        for row in account_rows
        if row["id"] in accounts_by_id
    ]
    return user_accounts + other_accounts


def get_account(account_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, label, secret_env_var FROM publishing_accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
    if row is not None:
        return {
            "id": row["id"],
            "label": row["label"],
            "configured": bool(os.getenv(row["secret_env_var"])),
        }

    with _connect() as conn:
        user = conn.execute(
            """
            SELECT persona_id, name, role, description, relationship, personality
            FROM users
            WHERE persona_id = ?
            """,
            (account_id,),
        ).fetchone()
    if user is None:
        return None
    return {
        "id": user["persona_id"],
        "label": user["name"],
        "name": user["name"],
        "role": user["role"],
        "description": user["description"],
        "relationship": user["relationship"],
        "personality": user["personality"],
        "configured": bool(os.getenv(f"DEV_TO_API_KEY_{account_id}")),
    }
