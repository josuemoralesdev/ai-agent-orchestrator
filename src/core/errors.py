from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OrchestratorError:
    code: str
    message: str
    detail: Optional[str] = None


UNKNOWN_TOOL = OrchestratorError(
    code="unknown_tool",
    message="Requested tool is not registered."
)