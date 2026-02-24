from fastapi import FastAPI
from pydantic import BaseModel
from src.core.models import AuditEvent, new_trace_id
from src.core.router import execute, route
from src.core.audit_store import append_events
from src.core.approval_store import write_pending
from src.tools.registry import build_registry
from src.core.approval_store import find_pending, mark_approved

app = FastAPI(title="AI Agent Orchestrator")
class InboundRequest(BaseModel):
    user_id: str
    message: str

class ApprovalRequest(BaseModel):
    approval_id: str

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/inbound")
async def inbound(req: InboundRequest):
    trace_id = new_trace_id()

    planned_tool, planned_args = route(req.message)

    audit = [
        AuditEvent.create(trace_id, "inbound_received", {"user_id": req.user_id}),
        AuditEvent.create(trace_id, "tool_planned", {"tool": planned_tool, "args": planned_args}),
    ]

    registry = build_registry()
    tool_obj = registry.get(planned_tool)

    if tool_obj and getattr(tool_obj, "requires_approval", False):
        approval_id = new_trace_id()  # separate id for approval tracking

    result = execute(planned_tool, planned_args)

    audit.append(
        AuditEvent.create(
            trace_id,
            "approval_required",
            {"approval_id": approval_id, "tool": planned_tool, "args": planned_args},
        )
    )

    # persist pending approval
    write_pending(
        {
            "approval_id": approval_id,
            "trace_id": trace_id,
            "tool": planned_tool,
            "args": planned_args,
            "status": "pending",
        }
    )

    append_events(audit)

    return {
        "trace_id": trace_id,
        "status": "pending_approval",
        "approval_id": approval_id,
        "tool": planned_tool,
        "planned_args": planned_args,
        "audit": [a.__dict__ for a in audit],
    }

@app.post("/approve")
async def approve(req: ApprovalRequest):
    pending = find_pending(req.approval_id)
    if not pending:
        return {"ok": False, "error": "approval_not_found"}

    tool = pending["tool"]
    args = pending["args"]
    trace_id = pending["trace_id"]

    result = execute(tool, args)

    mark_approved(req.approval_id)

    audit = [
        AuditEvent.create(trace_id, "approved", {"approval_id": req.approval_id}),
        AuditEvent.create(
            trace_id, "tool_executed", {"tool": result.tool, "ok": result.ok, "error": result.error}
        ),
    ]
    append_events(audit)

    return {"ok": True, "trace_id": trace_id, "result": result.__dict__}

@app.get("/")
async def root():
    return {"name": "AI Agent Orchestrator", "docs": "/docs", "health": "/health"}