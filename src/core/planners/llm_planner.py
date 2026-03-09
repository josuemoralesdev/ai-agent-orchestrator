from __future__ import annotations

from src.core.config import settings
from src.core.planner_types import Plan
from src.core.planners.base import BasePlanner
from src.core.planners.rule_planner import RulePlanner


class LLMPlanner(BasePlanner):
    def plan(self, *, user_id: str, message: str) -> Plan:
        """
        First live version:
        - if no API key, fallback to RulePlanner
        - later, replace fallback with actual OpenAI call
        """
        if not settings.openai_api_key:
            fallback = RulePlanner()
            plan = fallback.plan(user_id=user_id, message=message)
            plan.tool_call.reason = "llm_fallback_to_rule_no_api_key"
            return plan

        # Temporary guarded fallback until API call is wired
        fallback = RulePlanner()
        plan = fallback.plan(user_id=user_id, message=message)
        plan.tool_call.reason = "llm_placeholder_fallback"
        return plan