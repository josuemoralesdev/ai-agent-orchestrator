from __future__ import annotations

from typing import Any, Dict, List, Tuple

from src.core.models import AuditEvent
from src.core.router import execute  # adjust import if your execute lives elsewhere


def execute_tool_call(
    *,
    trace_id: str,
    tool: str,
    args: Dict[str, Any],
    audit: List[AuditEvent],
) -> Tuple[Dict[str, Any], List[AuditEvent]]:
    """
    Executes a planned tool call and appends a tool_executed audit event.
    Returns (result_dict, audit_list).
    """
    result = execute(tool, args)

    audit.append(
        AuditEvent.create(
            trace_id,
            "tool_executed",
            {"tool": result.tool, "ok": result.ok, "error": result.error},
        )
    )

    return result.__dict__, audit