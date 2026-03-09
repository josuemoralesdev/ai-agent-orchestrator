from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.planner_types import Plan


class BasePlanner(ABC):
    @abstractmethod
    def plan(self, *, user_id: str, message: str) -> Plan:
        raise NotImplementedError