from __future__ import annotations
from src.core.planner_types import Plan, ToolCall
from src.core.policy_resolver import requires_approval
from src.tools.registry import build_registry
from src.core.models import new_trace_id  # or wherever your trace_id helper is
from src.core.config import settings

def plan_next(*, user_id: str, message: str) -> Plan:
    trace_id = new_trace_id()

    # Use the existing router for now (keeps changes tiny)
    from src.core.router import route  # local import to avoid cycles
    tool, args = route(message)

    registry = build_registry()
    tool_obj = registry.get(tool)

    needs_approval = False
    if tool_obj:
        needs_approval = requires_approval(tool_obj, args, env=settings.env)

    tool_call = ToolCall(
        tool=tool,
        args=args,
        requires_approval=needs_approval,
        reason="rule_router_v1",
    )

    return Plan(
        trace_id=trace_id,
        user_id=user_id,
        message=message,
        tool_call=tool_call,
    )