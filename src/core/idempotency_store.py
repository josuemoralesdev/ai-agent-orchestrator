from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timezone, timedelta

import fcntl
from src.core.file_lock import locked_open

IDEMPOTENCY_PATH = Path("logs/idempotency.ndjson")


def ensure_log_dir() -> None:
    IDEMPOTENCY_PATH.parent.mkdir(parents=True, exist_ok=True)


def write_idempotency(key: str, response: Dict[str, Any]) -> None:
    ensure_log_dir()
    record = {"key": key, "ts": datetime.now(timezone.utc).isoformat(), "response": response}
    with locked_open(IDEMPOTENCY_PATH, "a", fcntl.LOCK_EX) as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def find_idempotency(key: str, *, ttl_seconds: int = 86400) -> Optional[Dict[str, Any]]:
    if not IDEMPOTENCY_PATH.exists():
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
    latest = None

    with locked_open(IDEMPOTENCY_PATH, "r", fcntl.LOCK_SH) as f:
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