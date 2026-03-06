from __future__ import annotations

import json
from src.core.db import get_conn


def get_trace_events(trace_id: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT trace_id, event_type, ts, payload_json
            FROM audit_events
            WHERE trace_id = ?
            ORDER BY id ASC
            """,
            (trace_id,),
        ).fetchall()

        return [
            {
                "trace_id": row["trace_id"],
                "event_type": row["event_type"],
                "ts": row["ts"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]
    finally:
        conn.close()


def list_approvals(status: str | None = None, limit: int = 20) -> list[dict]:
    conn = get_conn()
    try:
        if status:
            rows = conn.execute(
                """
                SELECT approval_id, trace_id, tool, status, created_at, updated_at
                FROM approvals
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT approval_id, trace_id, tool, status, created_at, updated_at
                FROM approvals
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_idempotency(limit: int = 20) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT key, created_at
            FROM idempotency
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        conn.close()