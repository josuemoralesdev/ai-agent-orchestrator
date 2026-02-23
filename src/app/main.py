from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AI Agent Orchestrator")


class InboundRequest(BaseModel):
    user_id: str
    message: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/inbound")
async def inbound(req: InboundRequest):
    """
    Minimal entry point for agent orchestration.

    Future flow:
    - intent extraction
    - tool routing
    - human-in-the-loop check
    - provider execution
    """
    return {
        "received": True,
        "user_id": req.user_id,
        "message": req.message,
        "next_step": "decision_layer_placeholder",
    }

@app.get("/")
async def root():
    return {"name": "AI Agent Orchestrator", "docs": "/docs", "health": "/health"}