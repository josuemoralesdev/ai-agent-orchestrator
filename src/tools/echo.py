from typing import Any, Dict

from src.core.models import ToolResult
from src.tools.base import Tool


class EchoTool(Tool):
    name = "echo"

    def run(self, *, args: Dict[str, Any]) -> ToolResult:
        # Deterministic, side-effect-free sample tool.
        return ToolResult(ok=True, tool=self.name, output={"echo": args})