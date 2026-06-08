import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.lane_outcome_enrichment import (
    CONFIRM_LANE_OUTCOME_ENRICHMENT_RECORDING_PHRASE,
    LANE_OUTCOME_ENRICHMENT_RECORDED,
    LANE_OUTCOME_ENRICHMENT_REJECTED,
    build_lane_outcome_enrichment,
    calculate_capture_readiness_score,
    calculate_combined_watch_score,
    calculate_outcome_coverage_pct,
    calculate_outcome_quality_score,
    classify_sample_size_bucket,
    classify_win_rate_quality_bucket,
    load_lane_outcome_enrichment_records,
)

NOW = datetime(2026, 6, 8, 18, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"
ALTERNATE = "BTCUSDT|55m|long|ladder_close_50_618"
NO_CAPTURE = "BTCUSDT|8m|short|fib_650"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_lane_outcome_enrichment(log_dir=log_dir, now=NOW)

    assert payload["enrichment_recorded"] is False
    assert payload["record_enrichment_requested"] is False
    assert load_lane_outcome_enrichment_records(log_dir=log_dir, limit=0) == []
    assert payload["target_scope"]["official_tiny_live_lane"] == OFFICIAL


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_lane_outcome_enrichment(
        log_dir=log_dir,
        record_enrichment=True,
        confirm_lane_outcome_enrichment="wrong",
        now=NOW,
    )

    assert payload["status"] == LANE_OUTCOME_ENRICHMENT_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["enrichment_recorded"] is False
    assert load_lane_outcome_enrichment_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_enrichment_only(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_lane_outcome_enrichment(
        log_dir=log_dir,
        record_enrichment=True,
        confirm_lane_outcome_enrichment=CONFIRM_LANE_OUTCOME_ENRICHMENT_RECORDING_PHRASE,
        now=NOW,
    )

    assert payload["status"] == LANE_OUTCOME_ENRICHMENT_RECORDED
    assert payload["enrichment_recorded"] is True
    records = load_lane_outcome_enrichment_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    assert records[0]["safety"]["config_written"] is False
    assert records[0]["safety"]["paper_outcome_ledger_rewritten"] is False
    assert records[0]["safety"]["order_placed"] is False


def test_sample_size_bucket_classification() -> None:
    assert classify_sample_size_bucket(0) == "NONE"
    assert classify_sample_size_bucket(1) == "TINY"
    assert classify_sample_size_bucket(29) == "TINY"
    assert classify_sample_size_bucket(30) == "SMALL"
    assert classify_sample_size_bucket(99) == "SMALL"
    assert classify_sample_size_bucket(100) == "MEDIUM"
    assert classify_sample_size_bucket(299) == "MEDIUM"
    assert classify_sample_size_bucket(300) == "LARGE"


def test_win_rate_quality_bucket_classification() -> None:
    assert classify_win_rate_quality_bucket(win_rate_pct=None, known_outcome_count=0) == "UNKNOWN"
    assert classify_win_rate_quality_bucket(win_rate_pct=54.99, known_outcome_count=10) == "WEAK"
    assert classify_win_rate_quality_bucket(win_rate_pct=55, known_outcome_count=10) == "MODERATE"
    assert classify_win_rate_quality_bucket(win_rate_pct=65, known_outcome_count=10) == "STRONG"
    assert classify_win_rate_quality_bucket(win_rate_pct=75, known_outcome_count=10) == "VERY_STRONG"


def test_outcome_coverage_calculation() -> None:
    assert calculate_outcome_coverage_pct(known_outcome_count=5, paper_outcome_count=10) == 50.0
    assert calculate_outcome_coverage_pct(known_outcome_count=0, paper_outcome_count=0) is None


def test_outcome_quality_score_deterministic() -> None:
    first = calculate_outcome_quality_score(
        win_rate_pct=72.5,
        known_outcome_count=120,
        paper_outcome_count=150,
        unknown_outcome_count=30,
        outcome_coverage_pct=80.0,
        outcome_freshness_status="fresh",
        blockers=["tiny_live_unique_capture_threshold_not_met"],
    )
    second = calculate_outcome_quality_score(
        win_rate_pct=72.5,
        known_outcome_count=120,
        paper_outcome_count=150,
        unknown_outcome_count=30,
        outcome_coverage_pct=80.0,
        outcome_freshness_status="fresh",
        blockers=["tiny_live_unique_capture_threshold_not_met"],
    )
    assert first == second


def test_capture_readiness_score_capped_at_one() -> None:
    assert calculate_capture_readiness_score(unique_capture_count=15, threshold_required_count=10) == 1.0


def test_combined_watch_score_deterministic() -> None:
    assert calculate_combined_watch_score(outcome_quality_score=60.0, capture_readiness_score=0.5) == 57.0
    assert calculate_combined_watch_score(outcome_quality_score=60.0, capture_readiness_score=0.5) == 57.0


def test_official_lane_remains_unchanged_and_no_promotion(tmp_path: Path) -> None:
    payload = build_lane_outcome_enrichment(log_dir=_fixture_logs(tmp_path), now=NOW)
    rows = {row["lane_key"]: row for row in payload["enriched_lane_rows"]}

    assert payload["target_scope"]["official_tiny_live_lane"] == OFFICIAL
    assert payload["official_tiny_live_lane_status"]["lane_key"] == OFFICIAL
    assert rows[OFFICIAL]["official_candidate"] is True
    assert payload["safety"]["official_tiny_live_lane_changed"] is False
    assert payload["safety"]["lane_promoted"] is False
    assert payload["safety"]["alternate_lane_promoted"] is False
    assert all(row["promotion_allowed"] is False for row in payload["enriched_lane_rows"])
    assert all(row["live_authorized"] is False for row in payload["enriched_lane_rows"])


def test_alternate_can_outrank_by_outcome_score_without_promotion(tmp_path: Path) -> None:
    payload = build_lane_outcome_enrichment(log_dir=_fixture_logs(tmp_path), now=NOW)
    rows = {row["lane_key"]: row for row in payload["enriched_lane_rows"]}

    assert rows[ALTERNATE]["outcome_quality_score"] > rows[OFFICIAL]["outcome_quality_score"]
    assert rows[ALTERNATE]["rank"] < rows[OFFICIAL]["rank"]
    assert payload["official_vs_alternate_comparison"]["alternate_outcome_edge_found"] is True
    assert rows[ALTERNATE]["promotion_allowed"] is False
    assert rows[ALTERNATE]["live_authorized"] is False


def test_win_rate_alone_does_not_imply_tiny_live_readiness(tmp_path: Path) -> None:
    payload = build_lane_outcome_enrichment(log_dir=_fixture_logs(tmp_path), now=NOW)
    row = {row["lane_key"]: row for row in payload["enriched_lane_rows"]}[NO_CAPTURE]

    assert row["win_rate_pct"] == 100.0
    assert row["capture_readiness_score"] == 0.0
    assert row["tiny_live_candidate_status"] == "CAPTURE_BLOCKED"
    assert "tiny_live_unique_capture_threshold_not_met" in row["blockers"]


def test_outcome_rows_without_unique_captures_remain_capture_blocked(tmp_path: Path) -> None:
    payload = build_lane_outcome_enrichment(log_dir=_fixture_logs(tmp_path), now=NOW)
    row = {row["lane_key"]: row for row in payload["enriched_lane_rows"]}[NO_CAPTURE]

    assert row["known_outcome_count"] > 0
    assert row["unique_capture_count"] == 0
    assert "unique_captures_missing" in row["blockers"]
    assert row["promotion_allowed"] is False


def test_safety_blocks_env_config_network_order_live_transfer_withdraw(tmp_path: Path) -> None:
    payload = build_lane_outcome_enrichment(log_dir=_fixture_logs(tmp_path), now=NOW)
    safety = payload["safety"]

    for key in (
        "env_written",
        "env_mutated",
        "config_written",
        "registry_config_written",
        "scoring_config_written",
        "matrix_config_written",
        "risk_contract_config_written",
        "lane_config_written",
        "ledger_rewritten",
        "destructive_write",
        "historical_ledger_rewritten",
        "paper_outcome_ledger_rewritten",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "order_payload_created",
        "executable_payload_created",
        "signed_order_request_created",
        "signed_trading_request_created",
        "signed_readonly_request_created",
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
        "official_tiny_live_lane_changed",
        "alternate_lane_promoted",
        "position_permission_created",
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
            "lane-outcome-enrichment",
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["target_scope"]["paper_only"] is True
    assert payload["enrichment_recorded"] is False


def _fixture_logs(tmp_path: Path) -> Path:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _append(
        log_dir / "full_spectrum_lane_scoreboard.ndjson",
        {
            "event_type": "FULL_SPECTRUM_LANE_SCOREBOARD",
            "scoreboard_id": "r231_fixture",
            "generated_at": NOW.isoformat(),
            "target_scope": {"official_tiny_live_lane": OFFICIAL, "paper_only": True, "live_authorized": False},
            "input_summary": {
                "paper_outcome_records_found": True,
                "tiny_live_capture_sync_found": True,
            },
            "official_tiny_live_lane_status": {
                "lane_key": OFFICIAL,
                "fresh_capture_count": 8,
                "required_fresh_capture_count": 10,
                "threshold_met": False,
                "threshold_distance_remaining": 2,
                "funding_should_wait": True,
                "risk_contract_should_wait": True,
            },
            "lane_scoreboard_rows": [
                _scoreboard_row(OFFICIAL, rank=1, unique=8, known=8, wins=6, losses=2, paper=10, unknown=2),
                _scoreboard_row(ALTERNATE, rank=2, unique=8, known=30, wins=26, losses=4, paper=30, unknown=0),
                _scoreboard_row(NO_CAPTURE, rank=3, unique=0, known=2, wins=2, losses=0, paper=2, unknown=0),
            ],
            "scoreboard_status": "OFFICIAL_TINY_LIVE_STILL_LEADING",
            "safety": {"official_tiny_live_lane_changed": False},
        },
    )
    _append(
        log_dir / "capture_count_sync_8m_short.ndjson",
        {
            "capture_count": {
                "fresh_capture_count": 8,
                "required_fresh_capture_count": 10,
                "threshold_met": False,
            },
            "watcher_status": {"watcher_likely_running": True, "watcher_stale": False},
        },
    )
    _append_outcomes(log_dir, OFFICIAL, wins=6, losses=2, unknown=2)
    _append_outcomes(log_dir, ALTERNATE, wins=26, losses=4, unknown=0)
    _append_outcomes(log_dir, NO_CAPTURE, wins=2, losses=0, unknown=0)
    return log_dir


def _scoreboard_row(
    lane_key: str,
    *,
    rank: int,
    unique: int,
    known: int,
    wins: int,
    losses: int,
    paper: int,
    unknown: int,
) -> dict:
    symbol, timeframe, direction, entry_mode = lane_key.split("|")
    return {
        "rank": rank,
        "lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "signal_flow_count": 0,
        "capture_event_count": unique,
        "unique_capture_count": unique,
        "latest_capture_at": "2026-06-08T17:00:00+00:00" if unique else None,
        "latest_outcome_at": "2026-06-08T17:30:00+00:00",
        "paper_outcome_count": paper,
        "known_outcome_count": known,
        "win_count": wins,
        "loss_count": losses,
        "outcome_unknown_count": unknown,
        "win_rate_pct": round((wins / known) * 100, 2) if known else None,
        "threshold_required_count": 10,
        "threshold_distance_remaining": max(0, 10 - unique),
        "tiny_live_candidate_status": "OFFICIAL_CANDIDATE" if lane_key == OFFICIAL else "TOO_FEW_UNIQUE_CAPTURES",
        "live_authorized": False,
        "promotion_allowed": False,
    }


def _append_outcomes(log_dir: Path, lane_key: str, *, wins: int, losses: int, unknown: int) -> None:
    symbol, timeframe, direction, entry_mode = lane_key.split("|")
    for index in range(wins):
        _append(log_dir / "outcomes.ndjson", _outcome(symbol, timeframe, direction, entry_mode, index, "win"))
    for index in range(losses):
        _append(log_dir / "outcomes.ndjson", _outcome(symbol, timeframe, direction, entry_mode, 100 + index, "loss"))
    for index in range(unknown):
        _append(log_dir / "outcomes.ndjson", _outcome(symbol, timeframe, direction, entry_mode, 200 + index, "unknown"))


def _outcome(symbol: str, timeframe: str, direction: str, entry_mode: str, index: int, outcome: str) -> dict:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "signal_id": f"{symbol}|{timeframe}|{direction}|2026-06-08T17:{index % 60:02d}:00+00:00",
        "outcome": outcome,
        "evaluated_at": "2026-06-08T17:30:00+00:00",
    }


def _append(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
