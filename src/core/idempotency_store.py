# src/core/idempotency_store.py
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from src.core.db import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_idempotency(scoped_key: str, ttl_seconds: int = 86400):
    """
    Return cached response for scoped key if still within TTL.
    """
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT response_json, created_at
            FROM idempotency
            WHERE key = ?
            """,
            (scoped_key,),
        ).fetchone()

        if not row:
            return None

        created_at = row["created_at"]
        created_dt = datetime.fromisoformat(created_at)

        if datetime.now(timezone.utc) - created_dt > timedelta(seconds=ttl_seconds):
            return None

        return json.loads(row["response_json"])

    finally:
        conn.close()


def write_idempotency(scoped_key: str, response: dict) -> None:
    """
    Upsert cached response for scoped key.
    """
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO idempotency (key, response_json, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                response_json=excluded.response_json,
                created_at=excluded.created_at
            """,
            (
                scoped_key,
                json.dumps(response),
                _now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()