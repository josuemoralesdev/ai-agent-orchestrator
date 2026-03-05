# src/core/sqlite_init.py
from __future__ import annotations

from src.core.db import get_conn


def init_db() -> None:
    """
    Create tables if they don't exist.
    Keep schema minimal & stable.
    """
    conn = get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                ts TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_trace_id ON audit_events(trace_id);")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                approval_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                tool TEXT NOT NULL,
                args_json TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_approvals_trace_id ON approvals(trace_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency (
                key TEXT PRIMARY KEY,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        conn.commit()
    finally:
        conn.close()