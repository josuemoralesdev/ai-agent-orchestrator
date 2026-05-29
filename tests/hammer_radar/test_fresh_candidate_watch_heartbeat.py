from __future__ import annotations

import json
from pathlib import Path

from src.app.hammer_radar.operator.watch_heartbeat import (
    HEARTBEAT_EVENT_TYPE,
    WATCH_ITERATION_COMPLETED,
    WATCH_ITERATION_STARTED,
    append_watch_heartbeat,
    build_watch_heartbeat_record,
    load_recent_ndjson_records,
    load_recent_watch_heartbeats,
    summarize_watch_heartbeats,
)


def test_heartbeat_records_append_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    first = build_watch_heartbeat_record(
        watch_id="watch-1",
        iteration=1,
        max_iterations=720,
        sleep_seconds=60,
        status=WATCH_ITERATION_STARTED,
    )
    second = build_watch_heartbeat_record(
        watch_id="watch-1",
        iteration=1,
        max_iterations=720,
        sleep_seconds=60,
        status=WATCH_ITERATION_COMPLETED,
        candidates_checked=3,
        fresh_normalized_count=1,
        stale_normalized_count=2,
    )

    append_watch_heartbeat(first, log_dir=log_dir)
    append_watch_heartbeat(second, log_dir=log_dir)

    records = load_recent_watch_heartbeats(log_dir=log_dir, limit=10)
    assert len(records) == 2
    assert records[0]["status"] == WATCH_ITERATION_COMPLETED
    assert records[1]["status"] == WATCH_ITERATION_STARTED
    assert records[0]["event_type"] == HEARTBEAT_EVENT_TYPE
    assert records[0]["candidates_checked"] == 3
    assert records[0]["safety"]["order_placed"] is False
    assert records[0]["safety"]["real_order_placed"] is False
    assert records[0]["safety"]["execution_attempted"] is False
    assert records[0]["safety"]["paper_live_separation_intact"] is True


def test_tail_reader_tolerates_malformed_lines(tmp_path: Path) -> None:
    path = tmp_path / "heartbeats.ndjson"
    path.write_text(
        "\n".join(
            [
                json.dumps({"status": "old"}),
                "{not json",
                json.dumps({"status": "newer"}),
                "",
                json.dumps({"status": "latest"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    records = load_recent_ndjson_records(path, limit=3)

    assert [row["status"] for row in records] == ["latest", "newer", "old"]


def test_heartbeat_summary_uses_recent_first_order(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    append_watch_heartbeat(
        build_watch_heartbeat_record(
            watch_id="watch-1",
            iteration=1,
            max_iterations=2,
            sleep_seconds=1,
            status=WATCH_ITERATION_STARTED,
        ),
        log_dir=log_dir,
    )
    append_watch_heartbeat(
        build_watch_heartbeat_record(
            watch_id="watch-1",
            iteration=1,
            max_iterations=2,
            sleep_seconds=1,
            status=WATCH_ITERATION_COMPLETED,
            paper_proof_captured=True,
            captured_lane_key="BTCUSDT|13m|long|ladder_close_50_618",
        ),
        log_dir=log_dir,
    )

    summary = summarize_watch_heartbeats(load_recent_watch_heartbeats(log_dir=log_dir, limit=10))

    assert summary["records_count"] == 2
    assert summary["last_status"] == WATCH_ITERATION_COMPLETED
    assert summary["paper_proof_captures_count"] == 1
    assert summary["last_captured_lane_key"] == "BTCUSDT|13m|long|ladder_close_50_618"
