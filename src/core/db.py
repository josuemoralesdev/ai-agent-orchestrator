# src/core/db.py
from __future__ import annotations

import sqlite3
from pathlib import Path

from src.core.config import settings


def _ensure_parent_dir(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)


def get_conn() -> sqlite3.Connection:
    """
    Returns a new sqlite connection.
    We use WAL for better concurrency behavior.
    """
    db_path = Path(settings.sqlite_db_path)
    _ensure_parent_dir(db_path)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Concurrency / durability basics
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    return conn