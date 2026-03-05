from fastapi import FastAPI
from pydantic import BaseModel
from src.core.models import AuditEvent, new_trace_id
from src.core.router import execute #, route
from src.core.audit_store import append_events
from src.core.approval_store import write_pending
#from src.tools.registry import build_registry
from src.core.approval_store import find_pending, mark_approved, mark_executed
#from src.core.policy_resolver import requires_approval
from src.core.config import settings
from src.core.planner import plan_next
from src.core.planner_types import Plan
from fastapi.responses import JSONResponse
from src.core.executor import execute_tool_call
from typing import Any, Dict
from fastapi import Header
from src.core.idempotency_store import find_idempotency, write_idempotency
from src.core.sqlite_init import init_db

app = FastAPI(title="AI Agent Orchestrator")

@app.on_event("startup")
def _startup() -> None:
    init_db()
class InboundRequest(BaseModel):
    user_id: str
    message: str

class ApprovalRequest(BaseModel):
    approval_id: str

class ExecuteRequest(BaseModel):
    trace_id: str
    tool: str
    args: Dict[str, Any] = {}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/inbound")
async def inbound(req: InboundRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):

    if idempotency_key:
        scoped_key = f"{req.user_id}:{idempotency_key}" if idempotency_key else None
        cached = find_idempotency(scoped_key)
        if cached is not None:
            # optional: you can add a flag so you know it was cached
            cached = dict(cached)
            cached["idempotency"] = {"hit": True, "key": idempotency_key, "scoped_key": scoped_key}
            return cached

    p = plan_next(user_id=req.user_id, message=req.message)
    trace_id = p.trace_id
    planned_tool = p.tool_call.tool
    planned_args = p.tool_call.args

    audit = [
        AuditEvent.create(trace_id, "inbound_received", {"user_id": req.user_id}),
        AuditEvent.create(trace_id, "tool_planned", {"tool": planned_tool, "args": planned_args}),
    ]

    if p.tool_call.policy_decision == "approval_required":
        approval_id = new_trace_id()  # separate id for approval tracking

        audit.append(
            AuditEvent.create(
                trace_id,
                "policy_decision",
                {
                #    "approval_id": approval_id, "tool": planned_tool, "args": planned_args
                "policy_decision": p.tool_call.policy_decision,
                "risk_level": p.tool_call.risk_level,
                "confidence": p.tool_call.confidence,
                "reason": p.tool_call.reason,
                },
            )
        )

        # persist pending approval
        write_pending(
            approval_id=approval_id,
            trace_id=trace_id,
            tool=planned_tool,
            args=planned_args,
        )

        append_events(audit)

        resp = {
            "trace_id": trace_id,
            "status": "pending_approval",
            "approval_id": approval_id,
            "tool": planned_tool,
            "planned_args": planned_args,
            "audit": [a.__dict__ for a in audit],
            "tool_call": p.tool_call.__dict__ if hasattr(p.tool_call, "__dict__") else p.tool_call,
        }

        if idempotency_key:
            scoped_key = f"{req.user_id}:{idempotency_key}"
            write_idempotency(scoped_key, resp)

        return resp

    # If no approval required, execute immediately
    result = execute(planned_tool, planned_args)

    audit.append(
        AuditEvent.create(
            trace_id,
            "tool_executed",
            {"tool": result.tool, "ok": result.ok, "error": result.error},
        )
    )

    append_events(audit)

    resp = {
        "trace_id": trace_id,
        "received": True,
        "user_id": req.user_id,
        "message": req.message,
        "tool": planned_tool,
        "result": result.__dict__,
        "audit": [a.__dict__ for a in audit],
        "tool_call": p.tool_call.__dict__ if hasattr(p.tool_call, "__dict__") else p.tool_call,
        "next_step": "decision_layer_llm_placeholder",
    }

    if idempotency_key:
        scoped_key = f"{req.user_id}:{idempotency_key}"
        write_idempotency(scoped_key, resp)

    return resp

@app.post("/approve")
async def approve(req: ApprovalRequest):
    rec = find_pending(req.approval_id)
    if not rec:
        return {"ok": False, "error": "approval_not_found"}

    #Idempotency Gate
    if rec.get("status") == "executed":
        return {
            "ok": True,
            "trace_id": rec.get("trace_id"),
            "result": rec.get("result"),
            "already_executed": True,
        }
    
    tool = rec["tool"]
    args = rec["args"]
    trace_id = rec["trace_id"]

    mark_approved(req.approval_id)

    audit = [
        AuditEvent.create(trace_id, "approved", {"approval_id": req.approval_id}),
    ]

    result_dict, audit = execute_tool_call(
    trace_id=trace_id,
    tool=tool,
    args=args,
    audit=audit,
    )

    append_events(audit)

    mark_executed(req.approval_id, result_dict)

    return {"ok": True, "trace_id": trace_id, "result": result_dict}

@app.post("/execute")
async def execute_endpoint(req: ExecuteRequest):
    audit = [
        AuditEvent.create(req.trace_id, "execute_requested", {"tool": req.tool}),
    ]

    result_dict, audit = execute_tool_call(
        trace_id=req.trace_id,
        tool=req.tool,
        args=req.args,
        audit=audit,
    )

    append_events(audit)

    return {
        "ok": True,
        "trace_id": req.trace_id,
        "result": result_dict,
        "audit": [a.__dict__ for a in audit],
    }

@app.get("/")
async def root():
    return {"name": "AI Agent Orchestrator", "docs": "/docs", "health": "/health"}

@app.post("/plan", response_model=Plan)
async def plan(req: InboundRequest):

    msg = (req.message or "").strip()
    if not msg:
        return JSONResponse(status_code=400, content={"ok": False, "error": "empty_message"})
    if len(msg) > 2000:
        return JSONResponse(status_code=400, content={"ok": False, "error": "message_too_long"})
    
    return plan_next(user_id=req.user_id, message=req.message)
