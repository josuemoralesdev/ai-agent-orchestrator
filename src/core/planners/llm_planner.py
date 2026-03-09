from __future__ import annotations

from src.core.planner_types import Plan
from src.core.planners.base import BasePlanner


class LLMPlanner(BasePlanner):
    def plan(self, *, user_id: str, message: str) -> Plan:
        """
        Placeholder for future LLM-backed planning.

        Expected future behavior:
        - call OpenAI API (or other model)
        - return the same Plan contract
        - produce tool, args, confidence, reason, policy hints
        """
        raise NotImplementedError("LLMPlanner is not wired yet")