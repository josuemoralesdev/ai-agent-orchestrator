from __future__ import annotations

from src.core.config import settings
from src.core.models import new_trace_id
from src.core.planner_types import Plan, ToolCall
from src.core.policy_resolver import requires_approval
from src.core.router import route
from src.core.planners.base import BasePlanner
from src.tools.registry import build_registry


class RulePlanner(BasePlanner):
    def plan(self, *, user_id: str, message: str) -> Plan:
        trace_id = new_trace_id()

        tool, args = route(message)

        registry = build_registry()
        tool_obj = registry.get(tool)

        risk = "unknown"
        if tool_obj and getattr(tool_obj, "risk", None):
            risk = str(tool_obj.risk.value) if hasattr(tool_obj.risk, "value") else str(tool_obj.risk)
        elif tool == "echo":
            risk = "safe"

        needs_approval = False
        if tool_obj:
            needs_approval = requires_approval(tool_obj, args, env=settings.env)

        policy_decision = "approval_required" if needs_approval else "auto"

        confidence = 0.6
        if tool == "echo":
            confidence = 0.95
        elif tool == "httpbin_get":
            confidence = 0.85

        tool_call = ToolCall(
            tool=tool,
            args=args,
            requires_approval=needs_approval,
            policy_decision=policy_decision,
            risk_level=risk,
            confidence=confidence,
            reason="rule_router_v1",
        )

        return Plan(
            trace_id=trace_id,
            user_id=user_id,
            message=message,
            tool_call=tool_call,
        )