from __future__ import annotations

from src.core.planner_types import Plan
from src.core.planners import RulePlanner


def get_planner():
    """
    Planner selector.
    For now: always RulePlanner.
    Later: return LLMPlanner / HybridPlanner based on settings.
    """
    return RulePlanner()


def plan_next(*, user_id: str, message: str) -> Plan:
    planner = get_planner()
    return planner.plan(user_id=user_id, message=message)