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

def get_approval(approval_id: str):
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT approval_id, trace_id, tool, args_json,
                   status, result_json, created_at, updated_at
            FROM approvals
            WHERE approval_id = ?
            """,
            (approval_id,),
        ).fetchone()

        if not row:
            return None

        return {
            "approval_id": row["approval_id"],
            "trace_id": row["trace_id"],
            "tool": row["tool"],
            "args": json.loads(row["args_json"]),
            "status": row["status"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()


def get_stats():
    conn = get_conn()
    try:
        return {
            "approvals_pending": conn.execute(
                "SELECT COUNT(*) FROM approvals WHERE status='pending'"
            ).fetchone()[0],
            "approvals_executed": conn.execute(
                "SELECT COUNT(*) FROM approvals WHERE status='executed'"
            ).fetchone()[0],
            "idempotency_keys": conn.execute(
                "SELECT COUNT(*) FROM idempotency"
            ).fetchone()[0],
            "audit_events": conn.execute(
                "SELECT COUNT(*) FROM audit_events"
            ).fetchone()[0],
        }
    finally:
        conn.close()