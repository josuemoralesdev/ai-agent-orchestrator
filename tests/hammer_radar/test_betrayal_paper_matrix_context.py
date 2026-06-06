from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_paper_matrix_context import (
    BETRAYAL_PAPER_MATRIX_CONTEXT_RECORDED,
    BETRAYAL_PAPER_MATRIX_CONTEXT_REJECTED,
    CONFIRM_BETRAYAL_PAPER_MATRIX_CONTEXT_RECORDING_PHRASE,
    LEDGER_FILENAME,
    build_betrayal_paper_matrix_context,
    load_betrayal_paper_matrix_context_records,
)

NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_paper_matrix_context(log_dir=log_dir, now=NOW)

    assert payload["record_matrix_requested"] is False
    assert payload["matrix_recorded"] is False
    assert payload["matrix_id"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_paper_matrix_context(
        log_dir=log_dir,
        record_matrix=True,
        confirm_betrayal_paper_matrix_context="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_PAPER_MATRIX_CONTEXT_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["matrix_recorded"] is False
    assert load_betrayal_paper_matrix_context_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_matrix_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    before_env = dict(os.environ)

    payload = build_betrayal_paper_matrix_context(
        log_dir=log_dir,
        record_matrix=True,
        confirm_betrayal_paper_matrix_context=CONFIRM_BETRAYAL_PAPER_MATRIX_CONTEXT_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_betrayal_paper_matrix_context_records(log_dir=log_dir, limit=0)

    assert payload["status"] == BETRAYAL_PAPER_MATRIX_CONTEXT_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["matrix_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_PAPER_MATRIX_CONTEXT"
    assert before_env == dict(os.environ)


def test_includes_betrayal_context_rows_and_refreshed_counts(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_paper_matrix_context(log_dir=log_dir, now=NOW)
    rows = {row["candidate"]: row for row in payload["betrayal_context_rows"]}

    assert rows["222m aggregate"]["label"] == "BETRAYAL_PRIMARY_CANDIDATE"
    assert rows["222m aggregate"]["resolved_true_inverse_samples"] == 15
    assert rows["222m aggregate"]["shadow_outcome_count"] == 20
    assert rows["222m aggregate"]["unresolved_shadow_samples"] == 5
    assert rows["88m aggregate"]["label"] == "BETRAYAL_WATCHLIST"
    assert rows["88m aggregate"]["resolved_true_inverse_samples"] == 32
    assert rows["55m aggregate"]["resolved_true_inverse_samples"] == 26
    assert rows["55m aggregate"]["paper_only"] is True


def test_compares_betrayal_to_normal_paper_references(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_paper_matrix_context(log_dir=log_dir, now=NOW)
    comparison = payload["betrayal_vs_normal_comparison"]

    assert comparison["normal_reference_rows"] == [
        {"name": "8m short + hammer_wick_reversal", "score": 84, "paper_only": True},
        {"name": "8m short + bearish_engulfing", "score": 82, "paper_only": True},
        {"name": "8m short + three_black_crows", "score": 68, "paper_only": True},
    ]
    assert comparison["betrayal_can_enter_paper_matrix"] is True
    assert comparison["betrayal_can_enter_live_readiness"] is False
    assert comparison["top_betrayal_candidate"] in {"222m aggregate", "88m aggregate", "55m aggregate"}


def test_marks_betrayal_paper_only_context_not_live_or_promoted(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_paper_matrix_context(log_dir=log_dir, now=NOW)

    assert payload["target_scope"]["paper_only"] is True
    assert payload["target_scope"]["live_authorized"] is False
    for row in payload["betrayal_context_rows"]:
        assert row["paper_only"] is True
        assert row["live_ready"] is False
        assert row["promotion_allowed"] is False
        assert row["live_authorized"] is False
        assert row["lane_mode_eligible"] is False
    assert payload["safety"]["betrayal_live_authorized"] is False
    assert payload["safety"]["betrayal_promoted"] is False


def test_identifies_event_tracker_regime_and_miro_gaps(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_paper_matrix_context(log_dir=log_dir, now=NOW)
    gap = payload["betrayal_matrix_gap_report"]
    actions = {row["recommended_action"] for row in payload["betrayal_context_recommendations"]}

    assert gap["event_tracker_missing"] is True
    assert gap["regime_gate_missing_or_pending"] is True
    assert gap["miro_fish_missing_or_pending"] is True
    assert gap["direction_split_missing"] is True
    assert gap["tiny_live_excluded"] is True
    assert "BUILD_BETRAYAL_EVENT_TRACKER" in actions
    assert "RUN_REGIME_GATE" in actions
    assert "RUN_MIRO_FISH_GATE" in actions


def test_no_env_config_destructive_network_binance_or_live_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    before_env = dict(os.environ)
    config_path = tmp_path / "configs" / "lane_controls.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    before_config = config_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_betrayal_paper_matrix_context(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_cli_exists(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "betrayal-paper-matrix-context",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    help_result = subprocess.run(
        [".venv/bin/python", "-m", "src.app.hammer_radar.operator.inspect", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert "betrayal_context_rows" in payload
    assert "betrayal-paper-matrix-context" in help_result.stdout


def _write_stack(log_dir: Path) -> None:
    _append_json(
        log_dir / "betrayal_true_inverse_refresh.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "candidate_true_inverse_summary": {
                "222m": _candidate("BETRAYAL_PRIMARY_CANDIDATE", 12.5, 87.5, 15, 20, 5),
                "88m": _candidate("BETRAYAL_WATCHLIST", 36.67, 63.33, 32, 46, 14),
                "55m": _candidate("BETRAYAL_OPTIONAL_WATCHLIST_FOUND_IN_HISTORY", None, None, 26, 52, 26),
            },
            "refresh_status": "TRUE_INVERSE_VALIDATION_REFRESHED",
            "safety": {"betrayal_live_authorized": False, "betrayal_promoted": False},
        },
    )
    _append_json(
        log_dir / "betrayal_integration_recheck.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "betrayal_candidate_summary": {
                "222m": {"label": "BETRAYAL_PRIMARY_CANDIDATE", "original_win_rate_pct": 12.5, "naive_inverse_win_rate_pct": 87.5},
                "88m": {"label": "BETRAYAL_WATCHLIST", "original_win_rate_pct": 36.67, "naive_inverse_win_rate_pct": 63.33},
                "55m": {"label": "BETRAYAL_OPTIONAL_WATCHLIST_FOUND_IN_HISTORY"},
            },
            "current_stack_gap_report": {
                "included_in_pattern_lane_matrix": False,
                "included_in_anchor_confluence_matrix": False,
                "included_in_tiny_live_readiness": False,
                "matrix_integration_missing": True,
            },
        },
    )
    _append_json(
        log_dir / "pattern_lane_matrix_review.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "pattern_lane_pair_matrix": [
                _normal_row("hammer_wick_reversal", 84),
                _normal_row("bearish_engulfing", 82),
                _normal_row("three_black_crows", 68),
                {"timeframe": "222m", "direction": "long", "signal_origin": "hammer_wick_reversal", "pair_score": 63},
                {"timeframe": "88m", "direction": "short", "signal_origin": "hammer_wick_reversal", "pair_score": 63},
                {"timeframe": "55m", "direction": "short", "signal_origin": "hammer_wick_reversal", "pair_score": 63},
            ],
        },
    )
    _append_json(
        log_dir / "anchor_signal_confluence_matrix.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "confluence_evidence_quality_report": {
                "summary_level_is_weaker_evidence": True,
                "event_level_rows": 0,
            },
            "anchor_signal_confluence_rows": [
                {"timeframe": "222m", "confluence_score": 60},
                {"timeframe": "88m", "confluence_score": 58},
            ],
            "anchor_signal_confluence_rankings": [{"confluence_score": 75}],
        },
    )
    _append_json(
        log_dir / "tiny_live_readiness_gap_recheck.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "candidate_context": {"primary_lane": "BTCUSDT|8m|short|ladder_close_50_618"},
            "evidence_stack_summary": {"primary_pair_score": 84},
        },
    )


def _candidate(
    label: str,
    original_win_rate: float | None,
    naive_inverse: float | None,
    resolved: int,
    shadow_count: int,
    unresolved: int,
) -> dict[str, object]:
    return {
        "label": label,
        "original_win_rate_pct": original_win_rate,
        "naive_inverse_win_rate_pct": naive_inverse,
        "resolved_true_inverse_samples": resolved,
        "shadow_outcome_count": shadow_count,
        "unresolved_shadow_samples": unresolved,
        "validation_status": "TRUE_INVERSE_VALIDATION_REFRESHED",
        "live_ready": False,
        "promotion_allowed": False,
    }


def _normal_row(origin: str, score: int) -> dict[str, object]:
    return {
        "timeframe": "8m",
        "direction": "short",
        "signal_origin": origin,
        "pair_score": score,
        "paper_only": True,
        "live_authorized": False,
    }


def _append_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
