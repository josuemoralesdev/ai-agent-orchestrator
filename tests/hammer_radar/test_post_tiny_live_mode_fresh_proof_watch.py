from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.post_tiny_live_mode_fresh_proof_watch import (
    CONFIRM_POST_TINY_LIVE_MODE_WATCH_RECORDING_PHRASE,
    POST_TINY_LIVE_MODE_WATCH_READY,
    POST_TINY_LIVE_MODE_WATCH_RECORDED,
    POST_TINY_LIVE_MODE_WATCH_REJECTED,
    SAFETY,
    build_post_tiny_live_mode_fresh_proof_watch_preview,
    load_post_tiny_live_mode_watch_records,
)
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE

LANE_13M = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_44M = "BTCUSDT|44m|long|ladder_close_50_618"


def test_preview_writes_no_record(monkeypatch: Any, tmp_path: Path) -> None:
    _stub_sources(monkeypatch)
    payload = _build(tmp_path)

    assert payload["status"] == POST_TINY_LIVE_MODE_WATCH_READY
    assert payload["record_watch_prep_requested"] is False
    assert payload["confirmation_valid"] is False
    assert payload["watch_prep_recorded"] is False
    assert payload["watch_prep_id"] is None
    assert set(payload["target_lanes"]) == {LANE_13M, LANE_44M}
    assert load_post_tiny_live_mode_watch_records(log_dir=tmp_path / "logs", limit=0) == []


def test_wrong_confirmation_rejects_record(monkeypatch: Any, tmp_path: Path) -> None:
    _stub_sources(monkeypatch)
    payload = _build(tmp_path, record_watch_prep=True, confirm_watch_prep="wrong")

    assert payload["status"] == POST_TINY_LIVE_MODE_WATCH_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["watch_prep_recorded"] is False
    assert load_post_tiny_live_mode_watch_records(log_dir=tmp_path / "logs", limit=0) == []


def test_exact_confirmation_records_watch_prep_only_append_only(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    _stub_sources(monkeypatch)

    first = _build(
        tmp_path,
        record_watch_prep=True,
        confirm_watch_prep=CONFIRM_POST_TINY_LIVE_MODE_WATCH_RECORDING_PHRASE,
    )
    second = _build(
        tmp_path,
        record_watch_prep=True,
        confirm_watch_prep=CONFIRM_POST_TINY_LIVE_MODE_WATCH_RECORDING_PHRASE,
    )

    assert first["status"] == POST_TINY_LIVE_MODE_WATCH_RECORDED
    assert second["status"] == POST_TINY_LIVE_MODE_WATCH_RECORDED
    assert first["watch_prep_recorded"] is True
    records = load_post_tiny_live_mode_watch_records(log_dir=tmp_path / "logs", limit=0)
    assert len(records) == 2
    assert records[0]["target_lanes"] == [LANE_13M, LANE_44M]
    assert records[0]["safety"]["order_placed"] is False
    assert records[0]["safety"]["config_written"] is False


def test_target_lanes_safe_watch_command_and_forbidden_commands(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    _stub_sources(monkeypatch)
    payload = _build(tmp_path)

    for lane_key in (LANE_13M, LANE_44M):
        lane = payload["lane_modes"][lane_key]
        assert lane["mode"] == "tiny_live"
        assert lane["is_target_tiny_live"] is True
        assert lane["status"] == "LANE_BLOCKED"
        assert "global gate not evaluated in fast lane status path" in lane["blockers"]
        assert "global first-live activation gate is not FIRST_LIVE_ACTIVATION_READY" in lane["blockers"]
        assert "global gate has not enabled execution" in lane["blockers"]

    assert "fresh-candidate-paper-proof-capture-loop" in payload["safe_watch_command"]
    assert "--max-iterations 60" in payload["safe_watch_command"]
    assert "--sleep-seconds 60" in payload["safe_watch_command"]
    commands = "\n".join([payload["safe_watch_command"], *payload["post_watch_recheck_commands"]])
    for forbidden in ("live-connector-submit", "global live flag arming", "kill switch disable"):
        assert forbidden not in commands
    assert payload["do_not_run_yet"] == [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
    ]


def test_safety_flags_all_false_except_separation(monkeypatch: Any, tmp_path: Path) -> None:
    _stub_sources(monkeypatch)
    payload = _build(tmp_path)

    for key, expected in SAFETY.items():
        assert payload["safety"][key] == expected, key
    assert payload["safety"]["paper_live_separation_intact"] is True
    assert payload["safety"]["order_placed"] is False
    assert payload["safety"]["real_order_placed"] is False
    assert payload["safety"]["execution_attempted"] is False
    assert payload["safety"]["order_payload_created"] is False
    assert payload["safety"]["network_allowed"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["global_live_flags_changed"] is False


def test_cli_exists() -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            "logs/hammer_radar_forward",
            "post-tiny-live-mode-fresh-proof-watch",
            "--all-target-lanes",
            "--include-watch-command",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={"PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] in {POST_TINY_LIVE_MODE_WATCH_READY, "POST_TINY_LIVE_MODE_WATCH_BLOCKED"}
    assert payload["target_lanes"] == [LANE_13M, LANE_44M]
    assert "fresh-candidate-paper-proof-capture-loop" in payload["safe_watch_command"]


def _build(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    kwargs = {
        "log_dir": tmp_path / "logs",
        "config_path": _write_config(tmp_path),
        "all_target_lanes": True,
        "include_watch_command": True,
        "live_eligibility_matrix": _matrix(),
    }
    kwargs.update(overrides)
    return build_post_tiny_live_mode_fresh_proof_watch_preview(**kwargs)


def _stub_sources(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "src.app.hammer_radar.operator.post_tiny_live_mode_fresh_proof_watch.build_binance_readonly_status",
        lambda: {
            "connector_status": "MISSING_ENV",
            "read_only": True,
            "api_key_present": False,
            "api_secret_present": False,
            "connector_mode": None,
            "blockers": ["BINANCE_CONNECTOR_MODE missing"],
            "warnings": ["BINANCE_API_KEY missing; signed read-only checks unavailable"],
        },
    )
    monkeypatch.setattr(
        "src.app.hammer_radar.operator.post_tiny_live_mode_fresh_proof_watch.build_post_bridge_watcher_proof_capture_recheck",
        lambda **kwargs: {
            "status": "POST_BRIDGE_RECHECK_READY",
            "next_operator_move": "WAIT_FOR_FRESH_NORMALIZED_CANDIDATE",
            "why": "stubbed",
            "normalized_candidate_visibility": {"fresh_visible_count": 0},
            "paper_capture_readiness": {"ready_lanes": []},
            "safety": dict(SAFETY),
        },
    )


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "lane_controls.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "default_mode": "disabled",
                "lanes": [
                    _lane("13m", 120),
                    _lane("44m", 300),
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _lane(timeframe: str, freshness_seconds: int) -> dict[str, Any]:
    return {
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "direction": "long",
        "entry_mode": "ladder_close_50_618",
        "mode": "tiny_live",
        "max_daily_trades": 1,
        "max_daily_loss_pct": 0.25,
        "freshness_seconds": freshness_seconds,
        "cooldown_after_loss_minutes": 120,
        "require_protective_orders": True,
    }


def _matrix() -> dict[str, Any]:
    return {
        "recommendations": [
            {
                "timeframe": "13m",
                "direction": "long",
                "entry_mode": "ladder_close_50_618",
                "recommendation": ELIGIBLE_FOR_FUTURE_TINY_LIVE,
                "sample_count": 50,
                "win_rate_pct": 60.0,
                "avg_pnl_pct": 0.2,
                "total_pnl_pct": 10.0,
                "blockers": [],
            },
            {
                "timeframe": "44m",
                "direction": "long",
                "entry_mode": "ladder_close_50_618",
                "recommendation": ELIGIBLE_FOR_FUTURE_TINY_LIVE,
                "sample_count": 50,
                "win_rate_pct": 60.0,
                "avg_pnl_pct": 0.2,
                "total_pnl_pct": 10.0,
                "blockers": [],
            },
        ]
    }
