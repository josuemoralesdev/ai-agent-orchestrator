from __future__ import annotations

import json

from openai import OpenAI

from src.core.config import settings
from src.core.planner_types import Plan, ToolCall
from src.core.planners.base import BasePlanner
from src.core.planners.rule_planner import RulePlanner
from src.core.policy_resolver import requires_approval
from src.tools.registry import build_registry
from src.core.models import new_trace_id


SYSTEM_PROMPT = """
You are a planning engine for a tool-using backend.

Your job:
- read the user's message
- choose exactly one tool
- produce strict JSON only

Allowed tools:
1. echo
   args:
   - message (string)

2. httpbin_get
   args:
   - url (string)

Rules:
- If the message is a simple greeting or plain text, use "echo"
- If the message contains an http/https URL and the user wants to check/fetch/call it, use "httpbin_get"
- Never invent tools
- Never return markdown
- Return JSON only with this shape:

{
  "tool": "echo" | "httpbin_get",
  "args": { ... },
  "confidence": 0.0,
  "reason": "short explanation"
}
""".strip()


class LLMPlanner(BasePlanner):
    def plan(self, *, user_id: str, message: str) -> Plan:
        """
        First real LLM-backed planner:
        - if no API key: fallback to RulePlanner
        - if LLM call fails or output is invalid: fallback to RulePlanner
        - policy is still enforced outside the model output
        """
        if not settings.openai_api_key:
            fallback = RulePlanner()
            plan = fallback.plan(user_id=user_id, message=message)
            plan.tool_call.reason = "llm_fallback_to_rule_no_api_key"
            return plan

        try:
            client = OpenAI(api_key=settings.openai_api_key)

            response = client.chat.completions.create(
                model=settings.planner_model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
            )

            content = response.choices[0].message.content or ""
            data = json.loads(content)

            tool = data.get("tool")
            args = data.get("args", {})
            confidence = float(data.get("confidence", 0.5))
            reason = str(data.get("reason", "llm_planner_v1"))

            if tool not in {"echo", "httpbin_get"}:
                raise ValueError(f"unsupported tool from llm: {tool}")

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

            tool_call = ToolCall(
                tool=tool,
                args=args,
                requires_approval=needs_approval,
                policy_decision=policy_decision,
                risk_level=risk,
                confidence=confidence,
                reason=reason,
            )

            return Plan(
                trace_id=new_trace_id(),
                user_id=user_id,
                message=message,
                tool_call=tool_call,
            )

        except Exception:
            fallback = RulePlanner()
            plan = fallback.plan(user_id=user_id, message=message)
            plan.tool_call.reason = "llm_fallback_to_rule_on_error"
            return plan