from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from src.core.models import ToolResult


class Tool(ABC):
    name: str

    @abstractmethod
    def run(self, *, args: Dict[str, Any]) -> ToolResult:
        raise NotImplementedError