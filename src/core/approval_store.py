import json
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.config import ensure_log_dir


PENDING_PATH = Path("logs/pending_approvals.ndjson")


def write_pending(approval: Dict[str, Any]) -> None:
    ensure_log_dir()
    with PENDING_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(approval, ensure_ascii=False) + "\n")


def find_pending(approval_id: str) -> Optional[Dict[str, Any]]:
    if not PENDING_PATH.exists():
        return None

    latest = None
    with PENDING_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("approval_id") == approval_id:
                latest = obj

    return latest


def mark_approved(approval_id: str) -> None:
    if not PENDING_PATH.exists():
        return

    # Rewrite file with status updated (simple approach)
    lines = PENDING_PATH.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            out.append(line)
            continue
        if obj.get("approval_id") == approval_id and obj.get("status") == "pending":
            obj["status"] = "approved"
            out.append(json.dumps(obj, ensure_ascii=False))
        else:
            out.append(line)
    PENDING_PATH.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")


def mark_executed(approval_id: str, result: Dict[str, Any]) -> None:
    rec = find_pending(approval_id)
    if not rec:
        return

    record = {
        "approval_id": approval_id,
        "trace_id": rec.get("trace_id"),
        "tool": rec.get("tool"),
        "args": rec.get("args"),
        "status": "executed",
        "result": result,
    }
    write_pending(record)