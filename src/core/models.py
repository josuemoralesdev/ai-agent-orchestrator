from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid


def new_trace_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class AuditEvent:
    trace_id: str
    event_type: str
    ts: str
    payload: Dict[str, Any]

    @staticmethod
    def create(trace_id: str, event_type: str, payload: Dict[str, Any]) -> "AuditEvent":
        return AuditEvent(
            trace_id=trace_id,
            event_type=event_type,
            ts=datetime.now(timezone.utc).isoformat(),
            payload=payload,
        )


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    tool: str
    output: Dict[str, Any]
    error: Optional[str] = None