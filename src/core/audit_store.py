from __future__ import annotations

import json
from typing import Any

from src.core.db import get_conn


def _event_to_row(ev: Any) -> tuple[str, str, str, str]:
    """
    Accepts either:
      - AuditEvent instance (with .trace_id, .event_type, .ts, .payload)
      - dict with keys: trace_id, event_type, ts, payload
    Returns tuple for DB insert.
    """
    if isinstance(ev, dict):
        trace_id = ev["trace_id"]
        event_type = ev["event_type"]
        ts = ev["ts"]
        payload = ev.get("payload", {})
    else:
        # AuditEvent object
        trace_id = ev.trace_id
        event_type = ev.event_type
        ts = ev.ts
        payload = getattr(ev, "payload", {}) or {}

    return trace_id, event_type, ts, json.dumps(payload)


def append_events(events: list[Any]) -> None:
    if not events:
        return

    conn = get_conn()
    try:
        for ev in events:
            trace_id, event_type, ts, payload_json = _event_to_row(ev)
            conn.execute(
                """
                INSERT INTO audit_events (trace_id, event_type, ts, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (trace_id, event_type, ts, payload_json),
            )
        conn.commit()
    finally:
        conn.close()