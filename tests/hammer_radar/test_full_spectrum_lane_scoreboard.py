import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import (
    ALTERNATE_CANDIDATES_FOUND,
    CONFIRM_FULL_SPECTRUM_LANE_SCOREBOARD_RECORDING_PHRASE,
    FULL_SPECTRUM_LANE_SCOREBOARD_RECORDED,
    FULL_SPECTRUM_LANE_SCOREBOARD_REJECTED,
    OFFICIAL_CANDIDATE,
    build_full_spectrum_lane_scoreboard,
    build_lane_capture_counts,
    build_lane_signal_counts,
    load_full_spectrum_lane_scoreboard_records,
    normalize_lane_key,
    parse_signal_id_for_lane,
)

NOW = datetime(2026, 6, 8, 16, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"
ALTERNATE = "BTCUSDT|22m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_full_spectrum_lane_scoreboard(log_dir=log_dir, now=NOW)

    assert payload["scoreboard_recorded"] is False
    assert payload["record_scoreboard_requested"] is False
    assert load_full_spectrum_lane_scoreboard_records(log_dir=log_dir, limit=0) == []
    assert payload["target_scope"]["official_tiny_live_lane"] == OFFICIAL


def test_wrong_confirmation_rejects_and_writes_no_record(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_full_spectrum_lane_scoreboard(
        log_dir=log_dir,
        record_scoreboard=True,
        confirm_full_spectrum_lane_scoreboard="wrong",
        now=NOW,
    )

    assert payload["status"] == FULL_SPECTRUM_LANE_SCOREBOARD_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["scoreboard_recorded"] is False
    assert load_full_spectrum_lane_scoreboard_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_scoreboard_only(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_full_spectrum_lane_scoreboard(
        log_dir=log_dir,
        record_scoreboard=True,
        confirm_full_spectrum_lane_scoreboard=CONFIRM_FULL_SPECTRUM_LANE_SCOREBOARD_RECORDING_PHRASE,
        now=NOW,
    )

    assert payload["status"] == FULL_SPECTRUM_LANE_SCOREBOARD_RECORDED
    assert payload["scoreboard_recorded"] is True
    records = load_full_spectrum_lane_scoreboard_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    assert records[0]["safety"]["config_written"] is False
    assert records[0]["safety"]["order_placed"] is False


def test_lane_key_normalization_and_missing_entry_mode() -> None:
    assert normalize_lane_key("btcusdt", "4H", "LONG", "ladder_close_50_618") == "BTCUSDT|4h|long|ladder_close_50_618"
    parsed = parse_signal_id_for_lane("BTCUSDT|8m|short|2026-06-08T00:00:00+00:00")
    assert parsed["lane_key"] == "BTCUSDT|8m|short|entry_unknown"
    assert parsed["entry_mode"] == "entry_unknown"


def test_signal_count_is_not_unique_capture_count_and_duplicates_are_deduped() -> None:
    signal_counts = build_lane_signal_counts(
        [
            {"lane_key": ALTERNATE, "signal_at": "2026-06-08T00:00:00+00:00"},
            {"lane_key": ALTERNATE, "signal_at": "2026-06-08T00:01:00+00:00"},
        ]
    )
    capture_counts = build_lane_capture_counts(
        [
            {"lane_key": ALTERNATE, "captured_signal_id": "sig-1", "capture_at": "2026-06-08T00:00:00+00:00"},
            {"lane_key": ALTERNATE, "captured_signal_id": "sig-1", "capture_at": "2026-06-08T00:01:00+00:00"},
        ]
    )

    assert signal_counts[ALTERNATE]["signal_flow_count"] == 2
    assert capture_counts[ALTERNATE]["capture_event_count"] == 2
    assert capture_counts[ALTERNATE]["unique_capture_count"] == 1


def test_alternate_candidates_reported_without_promotion_and_threshold_rules(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path, alternate_unique=10, official_unique=8, include_outcomes=False)

    payload = build_full_spectrum_lane_scoreboard(log_dir=log_dir, now=NOW)
    rows = {row["lane_key"]: row for row in payload["lane_scoreboard_rows"]}

    assert payload["scoreboard_status"] == ALTERNATE_CANDIDATES_FOUND
    assert payload["tiny_live_alternate_candidate_report"]["alternate_candidates_found"] is True
    assert rows[ALTERNATE]["unique_capture_count"] == 10
    assert rows[ALTERNATE]["threshold_distance_remaining"] == 0
    assert rows[ALTERNATE]["known_outcome_count"] == 0
    assert rows[ALTERNATE]["win_rate_pct"] is None
    assert all(row["live_authorized"] is False for row in payload["lane_scoreboard_rows"])
    assert all(row["promotion_allowed"] is False for row in payload["lane_scoreboard_rows"])
    assert payload["target_scope"]["official_tiny_live_lane"] == OFFICIAL
    assert rows[OFFICIAL]["tiny_live_candidate_status"] == OFFICIAL_CANDIDATE
    assert payload["safety"]["official_tiny_live_lane_changed"] is False
    assert payload["safety"]["alternate_lane_promoted"] is False


def test_safety_blocks_env_config_network_order_transfer_withdraw(tmp_path: Path) -> None:
    payload = build_full_spectrum_lane_scoreboard(log_dir=_fixture_logs(tmp_path), now=NOW)
    safety = payload["safety"]

    for key in (
        "env_written",
        "env_mutated",
        "config_written",
        "risk_contract_config_written",
        "lane_config_written",
        "ledger_rewritten",
        "destructive_write",
        "historical_ledger_rewritten",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "order_payload_created",
        "executable_payload_created",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "network_allowed",
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "secrets_shown",
        "global_live_flags_changed",
        "kill_switch_disabled",
        "live_authorization_created",
        "signal_origin_promoted",
        "lane_promoted",
    ):
        assert safety[key] is False
    assert safety["paper_live_separation_intact"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "full-spectrum-lane-scoreboard",
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["target_scope"]["paper_only"] is True
    assert payload["scoreboard_recorded"] is False


def _fixture_logs(
    tmp_path: Path,
    *,
    alternate_unique: int = 10,
    official_unique: int = 8,
    include_outcomes: bool = True,
) -> Path:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    for index in range(alternate_unique):
        _append(
            log_dir / "full_spectrum_harvester_expansion.ndjson",
            {
                "generated_at": f"2026-06-08T15:{index:02d}:00+00:00",
                "capture_summary": {
                    "captured_candidates": [
                        {
                            "lane_key": ALTERNATE,
                            "signal_id": f"BTCUSDT|22m|short|2026-06-08T15:{index:02d}:00+00:00",
                            "timestamp": f"2026-06-08T15:{index:02d}:00+00:00",
                        }
                    ]
                },
            },
        )
    for index in range(official_unique):
        _append(
            log_dir / "short_paper_evidence_capture.ndjson",
            {
                "paper_evidence_captured": True,
                "captured_lane_key": OFFICIAL,
                "captured_signal_id": f"BTCUSDT|8m|short|2026-06-08T14:{index:02d}:00+00:00",
                "recorded_at_utc": f"2026-06-08T14:{index:02d}:30+00:00",
            },
        )
    for index in range(12):
        _append(
            log_dir / "signals.ndjson",
            {
                "symbol": "BTCUSDT",
                "timeframe": "22m",
                "direction": "short",
                "signal_id": f"BTCUSDT|22m|short|2026-06-08T13:{index:02d}:00+00:00",
                "timestamp": f"2026-06-08T13:{index:02d}:00+00:00",
            },
        )
    if include_outcomes:
        _append(
            log_dir / "outcomes.ndjson",
            {
                "symbol": "BTCUSDT",
                "timeframe": "22m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "signal_id": "BTCUSDT|22m|short|2026-06-08T13:00:00+00:00",
                "outcome": "win",
                "evaluated_at": "2026-06-08T15:30:00+00:00",
            },
        )
    _append(
        log_dir / "capture_count_sync_8m_short.ndjson",
        {
            "capture_count": {
                "fresh_capture_count": official_unique,
                "required_fresh_capture_count": 10,
                "threshold_met": official_unique >= 10,
            },
            "watcher_status": {
                "watcher_likely_running": True,
                "watcher_stale": False,
            },
        },
    )
    return log_dir


def _append(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
