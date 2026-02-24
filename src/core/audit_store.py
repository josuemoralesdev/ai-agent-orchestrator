import json
from pathlib import Path
from typing import Iterable

from src.core.config import settings, ensure_log_dir
from src.core.models import AuditEvent


def append_events(events: Iterable[AuditEvent]) -> None:
    """
    Append audit events to an NDJSON file (one JSON object per line).
    This is intentionally simple and filesystem-based.
    """
    ensure_log_dir()
    path = Path(settings.audit_log_path)

    with path.open("a", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e.__dict__, ensure_ascii=False) + "\n")