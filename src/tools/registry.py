from typing import Dict

from src.tools.base import Tool
from src.tools.echo import EchoTool


def build_registry() -> Dict[str, Tool]:
    """
    Central place to register available tools.
    Later: load tools conditionally based on config.
    """
    tools: Dict[str, Tool] = {
        "echo": EchoTool(),
    }
    return tools