from fastapi import FastAPI
from pydantic import BaseModel
from src.core.models import AuditEvent, new_trace_id
from src.core.router import execute, route
from src.core.audit_store import append_events

app = FastAPI(title="AI Agent Orchestrator")


class InboundRequest(BaseModel):
    user_id: str
    message: str


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

    result = execute(planned_tool, planned_args)

    audit.append(
        AuditEvent.create(
            trace_id,
            "tool_executed",
            {"tool": result.tool, "ok": result.ok, "error": result.error},
        )
    )

    append_events(audit) 

    return {
        "trace_id": trace_id,
        "received": True,
        "user_id": req.user_id,
        "message": req.message,
        "tool": planned_tool,
        "result": result.__dict__,
        "audit": [a.__dict__ for a in audit],
        "next_step": "decision_layer_llm_placeholder",
    }

@app.get("/")
async def root():
    return {"name": "AI Agent Orchestrator", "docs": "/docs", "health": "/health"}