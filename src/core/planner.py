from __future__ import annotations

from src.core.planner_types import Plan
from src.core.planners import RulePlanner, LLMPlanner
from src.core.config import settings


def get_planner(kind: str | None = None):
    kind = kind or settings.planner_kind
    """
    Planner selector.

    Supported:
    - rule: deterministic rule-based planner
    - llm: placeholder for future LLM planner
    """
    if kind == "llm":
        return LLMPlanner()

    return RulePlanner()


def plan_next(*, user_id: str, message: str, planner_kind: str | None = None) -> Plan:
    planner = get_planner(planner_kind)
    return planner.plan(user_id=user_id, message=message)