"""SQLite persistence for generated content and its source request."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from .user_store import DB_PATH

_lock = threading.Lock()
DEFAULT_PLATFORMS = (("medium", "Medium"), ("dev.to", "Dev.to"), ("quora", "Quora"))


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
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS generations (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                request_json    TEXT    NOT NULL,
                result_json     TEXT    NOT NULL,
                raw_text        TEXT,
                title           TEXT,
                target_name     TEXT,
                platform        TEXT,
                persona_id      TEXT,
                writing_user    TEXT,
                word_count      INTEGER,
                generation_mode TEXT    NOT NULL DEFAULT 'generate',
                status          TEXT    NOT NULL DEFAULT 'completed',
                created_at      TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_generations_created_at
                ON generations(created_at DESC, id DESC);

            CREATE TABLE IF NOT EXISTS platforms (
                id         TEXT PRIMARY KEY,
                label      TEXT NOT NULL,
                enabled    INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        conn.executemany(
            "INSERT OR IGNORE INTO platforms (id, label, enabled) VALUES (?, ?, 1)",
            DEFAULT_PLATFORMS,
        )


def list_platforms() -> list[dict[str, str]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, label FROM platforms WHERE enabled = 1 ORDER BY rowid"
        ).fetchall()
    return [dict(row) for row in rows]


def save_generation(
    request: dict[str, Any],
    result: dict[str, Any],
    *,
    raw_text: str | None = None,
    generation_mode: str = "generate",
    status: str = "completed",
) -> int:
    target = request.get("target_person")
    target_name = target.get("name") if isinstance(target, dict) else None
    word_count = result.get("word_count")
    if not isinstance(word_count, int):
        word_count = None

    with _lock, _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO generations (
                request_json, result_json, raw_text, title, target_name, platform,
                persona_id, writing_user, word_count, generation_mode, status,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                json.dumps(request, ensure_ascii=False, default=str),
                json.dumps(result, ensure_ascii=False, default=str),
                raw_text,
                result.get("title"),
                target_name,
                result.get("platform") or request.get("platform"),
                request.get("persona_id"),
                result.get("writing_user"),
                word_count,
                generation_mode,
                status,
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
        return int(cursor.lastrowid)


def list_generations(limit: int = 25, offset: int = 0) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, title, target_name, platform, writing_user, word_count,
                   generation_mode, status, created_at
              FROM generations
             ORDER BY id DESC
             LIMIT ? OFFSET ?
            """,
            (safe_limit + 1, safe_offset),
        ).fetchall()

    has_more = len(rows) > safe_limit
    items = [dict(row) for row in rows[:safe_limit]]
    return {"items": items, "has_more": has_more}


def get_generation(generation_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM generations WHERE id = ?", (generation_id,)
        ).fetchone()
    if row is None:
        return None

    try:
        request = json.loads(row["request_json"])
    except (TypeError, json.JSONDecodeError):
        request = {}
    try:
        result = json.loads(row["result_json"])
    except (TypeError, json.JSONDecodeError):
        result = {"body_markdown": row["raw_text"] or ""}

    return {
        "id": row["id"],
        "request": request,
        "result": result,
        "raw_text": row["raw_text"],
        "generation_mode": row["generation_mode"],
        "status": row["status"],
        "created_at": row["created_at"],
    }
