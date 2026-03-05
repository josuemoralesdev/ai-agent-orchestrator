# src/core/approval_store.py
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.core.db import get_conn


def _now():
    return datetime.now(timezone.utc).isoformat()


def write_pending(approval_id: str, trace_id: str, tool: str, args: dict) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO approvals
            (approval_id, trace_id, tool, args_json, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                approval_id,
                trace_id,
                tool,
                json.dumps(args),
                _now(),
                _now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def find_pending(approval_id: str):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?",
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
        }
    finally:
        conn.close()


def mark_approved(approval_id: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE approvals
            SET status='approved', updated_at=?
            WHERE approval_id=? AND status='pending'
            """,
            (_now(), approval_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_executed(approval_id: str, result: dict) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE approvals
            SET status='executed', result_json=?, updated_at=?
            WHERE approval_id=?
            """,
            (json.dumps(result), _now(), approval_id),
        )
        conn.commit()
    finally:
        conn.close()