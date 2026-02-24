from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from src.core.models import ToolResult
from src.core.policy import RiskLevel


class Tool(ABC):
    name: str
    risk: RiskLevel = RiskLevel.SAFE

    @abstractmethod
    def run(self, *, args: Dict[str, Any]) -> ToolResult:
        raise NotImplementedError
    