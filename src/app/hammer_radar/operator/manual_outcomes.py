"""Manual outcome logging for Hammer Radar operator-only tiny-live reviews."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir

MANUAL_OUTCOMES_FILENAME = "manual_outcomes.ndjson"
VALID_MANUAL_OUTCOME_RESULTS = {"win", "loss", "breakeven", "skipped"}
LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False


def append_manual_outcome(
    *,
    signal_id: str,
    result: str,
    entry_price: float | None = None,
    exit_price: float | None = None,
    position_usd: float | None = None,
    leverage: float | None = None,
    pnl_usd: float | None = None,
    pnl_pct: float | None = None,
    notes: str = "",
    log_dir: str | Path | None = None,
) -> dict:
    if result not in VALID_MANUAL_OUTCOME_RESULTS:
        raise ValueError(f"invalid manual outcome result: {result}")
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    record = {
        "outcome_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "signal_id": signal_id,
        "result": result,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "position_usd": position_usd,
        "leverage": leverage,
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
        "notes": notes,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "source": "manual_outcome_log",
    }
    path = manual_outcomes_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def load_manual_outcomes(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict]:
    path = manual_outcomes_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if signal_id is not None and record.get("signal_id") != signal_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def build_manual_outcomes_text(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    log_dir: str | Path | None = None,
) -> str:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = load_manual_outcomes(limit=limit, signal_id=signal_id, log_dir=resolved_log_dir)
    lines = [
        "HAMMER RADAR MANUAL OUTCOMES",
        f"archive_log_dir: {resolved_log_dir}",
        "live_execution_enabled: false",
        "order_placed: false",
    ]
    if not records:
        return "\n".join([*lines, "no manual outcomes"])
    for record in records:
        lines.append(
            f"{record.get('created_at')} | {record.get('outcome_id')} | signal={record.get('signal_id')} | "
            f"result={record.get('result')} | pnl_usd={record.get('pnl_usd')} | pnl_pct={record.get('pnl_pct')} | "
            f"notes={record.get('notes', '')}"
        )
    return "\n".join(lines)


def manual_outcomes_path(log_dir: Path) -> Path:
    return log_dir / MANUAL_OUTCOMES_FILENAME
