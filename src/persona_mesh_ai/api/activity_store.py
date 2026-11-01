"""Audit trail, publishing history, and dashboard aggregates."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from .user_store import DB_PATH


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS activity_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id   TEXT,
                actor_id    TEXT,
                actor_name  TEXT,
                summary     TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_activity_created
                ON activity_events(created_at DESC, id DESC);

            CREATE TABLE IF NOT EXISTS publishing_history (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                generation_id     INTEGER,
                account_id        TEXT NOT NULL,
                account_name      TEXT NOT NULL,
                action            TEXT NOT NULL,
                status            TEXT NOT NULL,
                published         INTEGER NOT NULL DEFAULT 0,
                remote_article_id TEXT,
                article_url       TEXT,
                title             TEXT,
                post_json         TEXT NOT NULL DEFAULT '{}',
                result_json       TEXT NOT NULL DEFAULT '{}',
                created_at        TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_publishing_created
                ON publishing_history(created_at DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_publishing_draft_lookup
                ON publishing_history(generation_id, account_id, published, status, id DESC);
            """
        )


def log_event(
    event_type: str,
    entity_type: str,
    summary: str,
    *,
    entity_id: str | int | None = None,
    actor_id: str | None = None,
    actor_name: str | None = None,
    details: dict[str, Any] | None = None,
) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO activity_events (
                event_type, entity_type, entity_id, actor_id, actor_name,
                summary, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_type,
                entity_type,
                str(entity_id) if entity_id is not None else None,
                actor_id,
                actor_name,
                summary,
                json.dumps(details or {}, ensure_ascii=False, default=str),
                _now(),
            ),
        )
        return int(cursor.lastrowid)


def find_latest_draft(generation_id: int, account_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM publishing_history
             WHERE generation_id = ? AND account_id = ?
               AND status = 'success'
             ORDER BY id DESC LIMIT 1
            """,
            (generation_id, account_id),
        ).fetchone()
    if row is None or row["published"] or not row["remote_article_id"]:
        return None
    return dict(row)


def record_publishing(
    *,
    generation_id: int | None,
    account_id: str,
    account_name: str,
    action: str,
    post: dict[str, Any],
    result: dict[str, Any],
) -> int:
    published = bool(result.get("published"))
    article_id = result.get("article_id")
    title = result.get("title") or post.get("title")
    created_at = _now()
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO publishing_history (
                generation_id, account_id, account_name, action, status,
                published, remote_article_id, article_url, title, post_json,
                result_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                generation_id,
                account_id,
                account_name,
                action,
                result.get("status", "error"),
                int(published),
                str(article_id) if article_id is not None else None,
                result.get("article_url"),
                title,
                json.dumps(post, ensure_ascii=False, default=str),
                json.dumps(result, ensure_ascii=False, default=str),
                created_at,
            ),
        )
        history_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO activity_events (
                event_type, entity_type, entity_id, actor_id, actor_name,
                summary, details_json, created_at
            ) VALUES (?, 'publishing', ?, ?, ?, ?, ?, ?)
            """,
            (
                action,
                str(history_id),
                account_id,
                account_name,
                f"{action.replace('_', ' ').title()}: {title or 'Untitled'} ({result.get('status', 'error')})",
                json.dumps(
                    {
                        "generation_id": generation_id,
                        "status": result.get("status"),
                        "article_id": result.get("article_id"),
                        "article_url": result.get("article_url"),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                created_at,
            ),
        )
        return history_id


def list_activity(limit: int = 30) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 100))
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM activity_events ORDER BY id DESC LIMIT ?", (safe_limit,)
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        try:
            item["details"] = json.loads(item.pop("details_json"))
        except (TypeError, json.JSONDecodeError):
            item["details"] = {}
            item.pop("details_json", None)
        items.append(item)
    return items


def list_publishing_history(limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 100))
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM publishing_history ORDER BY id DESC LIMIT ?", (safe_limit,)
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        for source, target in (("post_json", "post"), ("result_json", "result")):
            try:
                item[target] = json.loads(item.pop(source))
            except (TypeError, json.JSONDecodeError):
                item[target] = {}
                item.pop(source, None)
        item["published"] = bool(item["published"])
        items.append(item)
    return items


def list_generation_publishing(generation_id: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT history.*
              FROM publishing_history AS history
              JOIN (
                    SELECT account_id, MAX(id) AS latest_id
                      FROM publishing_history
                     WHERE generation_id = ? AND status = 'success'
                     GROUP BY account_id
              ) AS latest ON latest.latest_id = history.id
             ORDER BY history.id DESC
            """,
            (generation_id,),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        try:
            item["result"] = json.loads(item.pop("result_json"))
        except (TypeError, json.JSONDecodeError):
            item["result"] = {}
            item.pop("result_json", None)
        item.pop("post_json", None)
        item["published"] = bool(item["published"])
        items.append(item)
    return items


def dashboard_summary() -> dict[str, Any]:
    with _connect() as conn:
        generations = conn.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed FROM generations"
        ).fetchone()
        publishing = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'success' AND published = 0
                       AND remote_article_id IS NOT NULL
                       AND NOT EXISTS (
                           SELECT 1 FROM publishing_history newer
                            WHERE newer.generation_id IS publishing_history.generation_id
                              AND newer.account_id = publishing_history.account_id
                              AND newer.status = 'success'
                              AND newer.id > publishing_history.id
                       ) THEN 1 ELSE 0 END) AS drafts,
                   SUM(CASE WHEN status = 'success' AND published = 1
                       AND NOT EXISTS (
                           SELECT 1 FROM publishing_history newer
                            WHERE newer.generation_id IS publishing_history.generation_id
                              AND newer.account_id = publishing_history.account_id
                              AND newer.status = 'success'
                              AND newer.id > publishing_history.id
                       ) THEN 1 ELSE 0 END) AS published,
                   SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS failed
              FROM publishing_history
            """
        ).fetchone()
        recent_generations = conn.execute(
            """
            SELECT id, title, target_name, platform, writing_user, status, created_at
              FROM generations ORDER BY id DESC LIMIT 8
            """
        ).fetchall()
        recent_publishing = conn.execute(
            """
            SELECT id, generation_id, account_name, action, status, published,
                   remote_article_id, article_url, title, created_at
              FROM publishing_history ORDER BY id DESC LIMIT 12
            """
        ).fetchall()
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    return {
        "metrics": {
            "users": int(user_count or 0),
            "generations": int(generations["total"] or 0),
            "completed_generations": int(generations["completed"] or 0),
            "drafts": int(publishing["drafts"] or 0),
            "published": int(publishing["published"] or 0),
            "publishing_errors": int(publishing["failed"] or 0),
        },
        "recent_generations": [dict(row) for row in recent_generations],
        "recent_publishing": [
            {**dict(row), "published": bool(row["published"])}
            for row in recent_publishing
        ],
        "activity": list_activity(20),
    }
