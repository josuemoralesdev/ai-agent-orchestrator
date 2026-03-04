from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timezone, timedelta

IDEMPOTENCY_PATH = Path("logs/idempotency.ndjson")


def ensure_log_dir() -> None:
    IDEMPOTENCY_PATH.parent.mkdir(parents=True, exist_ok=True)


def write_idempotency(key: str, response: Dict[str, Any]) -> None:
    """
    Append a cached response for an idempotency key.
    NDJSON append-only log.
    """
    ensure_log_dir()
    record = {"key": key, "ts": datetime.now(timezone.utc).isoformat(), "response": response}
    with IDEMPOTENCY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def find_idempotency(key: str, *, ttl_seconds: int = 86400) -> Optional[Dict[str, Any]]:
    
    """
    Return the most recent cached response for this key, if present.
    Linear scan is fine for demo; later becomes DB/Redis.
    """
    if not IDEMPOTENCY_PATH.exists():
        return None

    latest: Optional[Dict[str, Any]] = None
    with IDEMPOTENCY_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue

            if obj.get("key") == key:
                ts = obj.get("ts")
                # If ts exists, enforce TTL
                if ts:
                    try:
                        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                        if datetime.now(timezone.utc) - dt > timedelta(seconds=ttl_seconds):
                            continue  # expired cache entry
                    except Exception:
                        continue  # bad ts -> ignore this entry
                latest = obj.get("response")
                
    return latest