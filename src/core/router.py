from typing import Any, Dict, Tuple

from src.core.errors import UNKNOWN_TOOL
from src.core.models import ToolResult
from src.tools.registry import build_registry


def route(message: str) -> Tuple[str, Dict[str, Any]]:
    """
    Placeholder router.
    Later: LLM decides tool + args.
    Now: always selects echo tool.
    """
    return "echo", {"message": message}


def execute(tool_name: str, args: Dict[str, Any]) -> ToolResult:
    registry = build_registry()
    tool = registry.get(tool_name)

    if not tool:
        return ToolResult(
            ok=False,
            tool=tool_name,
            output={},
            error=UNKNOWN_TOOL.code
        )

    return tool.run(args=args)