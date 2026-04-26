"""Shared Hammer Radar operator log path resolution."""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
DEFAULT_LOG_DIR = ROOT_DIR / "logs" / "hammer_radar"
LOG_DIR_ENV_VAR = "HAMMER_RADAR_LOG_DIR"


def resolve_log_dir(log_dir: str | Path | None = None, *, default: Path = DEFAULT_LOG_DIR) -> Path:
    """Resolve the Hammer Radar log directory without creating it."""
    configured = log_dir if log_dir is not None else os.environ.get(LOG_DIR_ENV_VAR)
    if configured in (None, ""):
        return default
    return Path(configured).expanduser()
