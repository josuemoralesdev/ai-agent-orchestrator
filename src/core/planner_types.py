from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional

class ToolCall(BaseModel):
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    reason: Optional[str] = None

class Plan(BaseModel):
    trace_id: str
    user_id: str
    message: str
    tool_call: ToolCall