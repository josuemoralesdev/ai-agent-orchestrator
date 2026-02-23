from typing import Any, Dict, Tuple

from src.core.errors import UNKNOWN_TOOL
from src.core.models import ToolResult
from src.tools.registry import build_registry


def route(message: str) -> Tuple[str, Dict[str, Any]]:
    msg = message.lower().strip()

    if msg.startswith("http "):
        # Example: "http https://httpbin.org/get"
        parts = msg.split(maxsplit=1)
        url = parts[1] if len(parts) > 1 else "https://httpbin.org/get"
        return "httpbin_get", {"url": url}

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