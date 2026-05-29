from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.lane_control import build_lane_control_status
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE

LANE_13M = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_44M = "BTCUSDT|44m|long|ladder_close_50_618"


def test_lane_control_status_tiny_live_uses_fast_sentinel(monkeypatch: Any, tmp_path: Path) -> None:
    _block_heavy_global_gate(monkeypatch)
    payload = build_lane_control_status(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path),
        live_eligibility_matrix=_matrix(),
    )

    lanes = {row["lane_key"]: row for row in payload["lanes"]}
    for lane_key in (LANE_13M, LANE_44M):
        lane = lanes[lane_key]
        assert lane["mode"] == "tiny_live"
        assert lane["status"] == "LANE_BLOCKED"
        assert "global gate not evaluated in fast lane status path" in lane["blockers"]
        assert "global first-live activation gate is not FIRST_LIVE_ACTIVATION_READY" in lane["blockers"]
        assert "global gate has not enabled execution" in lane["blockers"]
        assert lane["safety"] == {
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "order_payload_created": False,
            "network_allowed": False,
            "secrets_shown": False,
        }

    assert payload["safety"] == {
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "order_payload_created": False,
        "network_allowed": False,
        "secrets_shown": False,
    }


def test_lane_control_status_default_does_not_call_first_live_activation_gate(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    _block_heavy_global_gate(monkeypatch)

    payload = build_lane_control_status(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path),
        live_eligibility_matrix=_matrix(),
        deep_global_gate_review=False,
    )

    assert payload["status_counts"]["LANE_BLOCKED"] == 2
    assert any(
        row["blocker"] == "global gate not evaluated in fast lane status path"
        for row in payload["top_blockers"]
    )


def test_lane_control_status_deep_review_is_explicit(monkeypatch: Any, tmp_path: Path) -> None:
    called = {"count": 0}

    def fake_gate(*args: object, **kwargs: object) -> dict[str, Any]:
        called["count"] += 1
        return {
            "status": "FIRST_LIVE_BLOCKED",
            "execution_enabled_by_gate": False,
            "blockers": ["deep gate reviewed"],
        }

    monkeypatch.setattr("src.app.hammer_radar.operator.lane_control._load_global_gate", fake_gate)

    payload = build_lane_control_status(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path),
        live_eligibility_matrix=_matrix(),
        deep_global_gate_review=True,
    )

    assert called["count"] == 2
    lanes = {row["lane_key"]: row for row in payload["lanes"]}
    assert "deep gate reviewed" in lanes[LANE_13M]["blockers"]
    assert "global gate not evaluated in fast lane status path" not in lanes[LANE_13M]["blockers"]


def _block_heavy_global_gate(monkeypatch: Any) -> None:
    def fail_gate(*args: object, **kwargs: object) -> None:
        raise AssertionError("heavy first-live activation gate must not be called")

    monkeypatch.setattr("src.app.hammer_radar.operator.lane_control._load_global_gate", fail_gate)
    monkeypatch.setattr(
        "src.app.hammer_radar.operator.first_live_activation_gate.build_first_live_activation_gate",
        fail_gate,
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
