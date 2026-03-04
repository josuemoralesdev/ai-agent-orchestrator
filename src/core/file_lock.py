from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO
import fcntl


@contextmanager
def locked_open(path: Path, mode: str, lock_type: int) -> Iterator[TextIO]:
    """
    Open a file and hold an advisory POSIX lock for the duration.
    lock_type: fcntl.LOCK_EX (exclusive) or fcntl.LOCK_SH (shared)
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    f = path.open(mode, encoding="utf-8")
    try:
        fcntl.flock(f.fileno(), lock_type)
        yield f
    finally:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            f.close()