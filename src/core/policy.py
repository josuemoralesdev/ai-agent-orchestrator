from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict
from urllib.parse import urlparse

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
        if self.risk == RiskLevel.SAFE:
            return False

    # Dev shortcut: allowlist external domains for EXTERNAL_CALL
        if env == "dev" and self.risk == RiskLevel.EXTERNAL_CALL:
            url = (args or {}).get("url")
            if isinstance(url, str) and url:
                host = (urlparse(url).hostname or "").lower()
                from src.core.config import allowlist_domains
                if host in allowlist_domains():
                    return False

        return True