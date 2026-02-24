from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class RiskLevel(str, Enum):
    SAFE = "safe"
    EXTERNAL_CALL = "external_call"
    PAYMENT = "payment"
    ACCOUNT_CHANGE = "account_change"


@dataclass(frozen=True)
class ToolPolicy:
    tool: str
    risk: RiskLevel

    def requires_approval(self, *, args: Dict[str, Any], env: str = "dev") -> bool:
        """
        Minimal rules:
        - SAFE: never requires approval
        - Everything else: requires approval in all envs (simple)
        Later: dev can auto-approve some classes, or allowlists by domain.
        """
        if self.risk == RiskLevel.SAFE:
            return False
        return True