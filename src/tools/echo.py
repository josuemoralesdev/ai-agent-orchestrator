from typing import Any, Dict

from src.core.models import ToolResult
from src.tools.base import Tool
from src.core.policy import RiskLevel


class EchoTool(Tool):
    name = "echo"
    risk = RiskLevel.SAFE

    def run(self, *, args: Dict[str, Any]) -> ToolResult:
        # Deterministic, side-effect-free sample tool.
        return ToolResult(ok=True, tool=self.name, output={"echo": args})