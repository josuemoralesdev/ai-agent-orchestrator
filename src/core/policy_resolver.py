from typing import Dict

from src.core.policy import RiskLevel, ToolPolicy
from src.tools.base import Tool


def policy_for(tool: Tool) -> ToolPolicy:
    """
    Central place to interpret tool metadata into policy.
    Later: load policy overrides from config.
    """
    return ToolPolicy(tool=tool.name, risk=getattr(tool, "risk", RiskLevel.SAFE))


def requires_approval(tool: Tool, args: Dict, env: str = "dev") -> bool:
    return policy_for(tool).requires_approval(args=args, env=env)