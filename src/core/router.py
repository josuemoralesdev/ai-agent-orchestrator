from typing import Any, Dict, Tuple

from src.core.models import ToolResult
from src.tools.echo import EchoTool


def route(message: str) -> Tuple[str, Dict[str, Any]]:
    """
    Placeholder router.
    Later: LLM decides tool + args.
    Now: always selects echo tool.
    """
    return "echo", {"message": message}


def execute(tool_name: str, args: Dict[str, Any]) -> ToolResult:
    # Minimal registry (expand later)
    registry = {
        "echo": EchoTool(),
    }
    tool = registry.get(tool_name)
    if not tool:
        return ToolResult(ok=False, tool=tool_name, output={}, error="unknown_tool")
    return tool.run(args=args)