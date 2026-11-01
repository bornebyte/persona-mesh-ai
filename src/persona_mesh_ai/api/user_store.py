"""SQLite-backed storage for persona users."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DB_PATH = Path(os.getenv("PM_USERS_DB", "persona_mesh_users.db")).resolve()

_lock = threading.Lock()
_DIGEST_PREFIX = "sha256$"


def _api_key_digest(api_key: str) -> str:
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return f"{_DIGEST_PREFIX}{digest}"


def _is_api_key_digest(value: str) -> bool:
    return bool(re.fullmatch(r"sha256\$[0-9a-f]{64}", value))


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Create the user table and migrate records from the previous profile shape."""
    with _lock, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                persona_id    TEXT,
                api_key       TEXT    NOT NULL UNIQUE,
                name          TEXT    NOT NULL,
                role          TEXT    NOT NULL DEFAULT '',
                description   TEXT    NOT NULL DEFAULT '',
                relationship  TEXT    NOT NULL DEFAULT '',
                personality   TEXT    NOT NULL DEFAULT '',
                email         TEXT    UNIQUE,
                notes         TEXT,
                profile_json  TEXT    NOT NULL DEFAULT '{}',
                created_at    TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL
            );
            """
        )

        # Older versions used an integer database id and stored persona details
        # in profile_json. Keep those records and assign their existing id as a
        # string persona id while adding the direct persona fields.
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        migrations = {
            "persona_id": "TEXT",
            "role": "TEXT NOT NULL DEFAULT ''",
            "description": "TEXT NOT NULL DEFAULT ''",
            "relationship": "TEXT NOT NULL DEFAULT ''",
            "personality": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in migrations.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")

        conn.execute(
            "UPDATE users SET persona_id = CAST(id AS TEXT) "
            "WHERE persona_id IS NULL OR persona_id = ''"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_persona_id "
            "ON users(persona_id)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key)")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    # The integer row id remains an internal storage detail. The API exposes
    # the persona's stable string id and never returns the stored API key.
    return {
        "id": row["persona_id"],
        "name": row["name"],
        "role": row["role"],
        "description": row["description"],
        "relationship": row["relationship"],
        "personality": row["personality"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_users() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_user(user_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE persona_id = ?", (user_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_user_by_api_key(api_key: str) -> dict[str, Any] | None:
    if not api_key:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE api_key IN (?, ?)",
            (api_key, _api_key_digest(api_key)),
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_user_api_key(user_id: str) -> str | None:
    """Return the stored publisher key when available; legacy digests are irreversible."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT api_key FROM users WHERE persona_id = ?", (user_id,)
        ).fetchone()
    if row is None or _is_api_key_digest(row["api_key"]):
        return None
    return row["api_key"]


def _normalize_user_payload(payload: dict[str, Any]) -> dict[str, str]:
    persona_id = str(payload.get("id") or "").strip()
    api_key = str(payload.get("api_key") or "").strip()
    fields = {
        field: str(payload.get(field) or "").strip()
        for field in (
            "name",
            "role",
            "description",
            "relationship",
            "personality",
        )
    }
    if not persona_id:
        raise ValueError("id is required")
    if not api_key:
        raise ValueError("api_key is required")
    for field, value in fields.items():
        if not value:
            raise ValueError(f"{field} is required")

    return {
        "id": persona_id,
        "api_key": api_key,
        **fields,
    }


def create_users(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Insert a batch atomically; any invalid row or conflict leaves no partial writes."""
    if not payloads:
        raise ValueError("At least one user is required")

    normalized = [_normalize_user_payload(payload) for payload in payloads]
    now = _now()
    with _lock, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for user in normalized:
                conn.execute(
                    """
                    INSERT INTO users (
                        persona_id, api_key, name, role, description,
                        relationship, personality, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user["id"],
                        user["api_key"],
                        user["name"],
                        user["role"],
                        user["description"],
                        user["relationship"],
                        user["personality"],
                        now,
                        now,
                    ),
                )

            created = [
                _row_to_dict(
                    conn.execute(
                        "SELECT * FROM users WHERE persona_id = ?", (user["id"],)
                    ).fetchone()
                )
                for user in normalized
            ]
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            if "persona_id" in str(exc):
                raise ValueError("id already exists") from exc
            if "api_key" in str(exc):
                raise ValueError("api_key already exists") from exc
            raise
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    return created


def create_user(payload: dict[str, Any]) -> dict[str, Any]:
    return create_users([payload])[0]


def update_user(user_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    existing = get_user(user_id)
    if existing is None:
        return None

    new_user_id = str(payload.get("id", user_id) or "").strip()
    if not new_user_id:
        raise ValueError("id cannot be empty")

    fields = {
        field: existing[field]
        for field in ("name", "role", "description", "relationship", "personality")
    }
    for field in fields:
        if field in payload:
            value = str(payload[field] or "").strip()
            if not value:
                raise ValueError(f"{field} cannot be empty")
            fields[field] = value

    api_key = payload.get("api_key")
    if api_key is not None:
        api_key = str(api_key).strip()
        if not api_key:
            raise ValueError("api_key cannot be empty")

    now = _now()
    with _lock, _connect() as conn:
        try:
            if api_key is None:
                conn.execute(
                    """
                    UPDATE users
                       SET persona_id = ?, name = ?, role = ?, description = ?, relationship = ?,
                           personality = ?, updated_at = ?
                     WHERE persona_id = ?
                    """,
                    (
                        new_user_id,
                        fields["name"],
                        fields["role"],
                        fields["description"],
                        fields["relationship"],
                        fields["personality"],
                        now,
                        user_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE users
                       SET persona_id = ?, api_key = ?, name = ?, role = ?, description = ?,
                           relationship = ?, personality = ?, updated_at = ?
                     WHERE persona_id = ?
                    """,
                    (
                        new_user_id,
                        api_key,
                        fields["name"],
                        fields["role"],
                        fields["description"],
                        fields["relationship"],
                        fields["personality"],
                        now,
                        user_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "api_key" in str(exc):
                raise ValueError("api_key already exists") from exc
            if "persona_id" in str(exc):
                raise ValueError("id already exists") from exc
            raise

    return get_user(new_user_id)


def delete_user(user_id: str) -> bool:
    with _lock, _connect() as conn:
        cur = conn.execute("DELETE FROM users WHERE persona_id = ?", (user_id,))
    return cur.rowcount > 0
