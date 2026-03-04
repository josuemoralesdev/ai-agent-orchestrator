import json
from pathlib import Path
from typing import Iterable

from src.core.config import settings, ensure_log_dir
from src.core.models import AuditEvent

import fcntl
from src.core.file_lock import locked_open

def append_events(events: list[AuditEvent]) -> None:

    ensure_log_dir()
    with locked_open(Path(settings.audit_log_path), "a", fcntl.LOCK_EX) as f:
        for ev in events:
            f.write(json.dumps(ev.__dict__, ensure_ascii=False) + "\n") # or your json.dumps(ev.__dict__)