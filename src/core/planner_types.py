from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional

class ToolCall(BaseModel):
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)

    # policy outcome
    requires_approval: bool = False
    policy_decision: str = "auto"  # "auto" | "approval_required"

    # planner signals (LLM-ready)
    risk_level: str = "safe"       # "safe" | "external_call" | ...
    confidence: float = 0.7        # 0.0 - 1.0

    # explanation/debug
    reason: Optional[str] = None


class Plan(BaseModel):
    trace_id: str
    user_id: str
    message: str
    tool_call: ToolCall