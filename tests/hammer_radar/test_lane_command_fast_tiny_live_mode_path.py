from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.lane_command_interface import (
    CONFIRM_LANE_CHANGE_PHRASE,
    LANE_COMMAND_APPLIED,
    LANE_COMMAND_PREVIEW,
    LANE_COMMAND_REJECTED,
    TINY_LIVE_LANE_WAITING_FOR_CONDITIONS,
    apply_lane_command,
)
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE


LANE_13M = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_44M = "BTCUSDT|44m|long|ladder_close_50_618"
SENTINEL_STATUS = "GLOBAL_GATE_NOT_EVALUATED_FAST_LANE_MODE_PATH"


def test_preview_set_mode_tiny_live_13m_uses_fast_sentinel(monkeypatch: Any, tmp_path: Path) -> None:
    _block_heavy_global_gate(monkeypatch)
    config_path = _write_config(tmp_path)

    payload = _command(config_path, tmp_path, lane_key=LANE_13M)

    assert payload["status"] == LANE_COMMAND_PREVIEW
    assert payload["previous_mode"] == "armed_dry_run"
    assert payload["requested_mode"] == "tiny_live"
    assert payload["resulting_mode"] == "tiny_live"
    assert payload["apply_requested"] is False
    assert payload["config_written"] is False
    assert payload["lane_mode_intent_state"] == TINY_LIVE_LANE_WAITING_FOR_CONDITIONS
    assert payload["lane_status_after_change"]["status"] == "LANE_BLOCKED"
    assert payload["global_gate_status"]["status"] == SENTINEL_STATUS
    assert "global gate not evaluated in fast lane mode path" in payload["global_gate_status"]["blockers"]
    assert "lane mode is operator intent only; it is not execution permission" in payload["warnings"]
    assert "global gates were not deeply evaluated in fast lane mode path" in payload["warnings"]
    assert "live execution remains disabled" in payload["warnings"]
    assert "global kill switch remains authoritative" in payload["warnings"]
    assert _read_config(config_path)["lanes"][0]["mode"] == "armed_dry_run"


def test_preview_set_mode_tiny_live_44m_uses_fast_sentinel(monkeypatch: Any, tmp_path: Path) -> None:
    _block_heavy_global_gate(monkeypatch)
    config_path = _write_config(tmp_path)

    payload = _command(config_path, tmp_path, lane_key=LANE_44M)

    assert payload["status"] == LANE_COMMAND_PREVIEW
    assert payload["previous_mode"] == "paper"
    assert payload["requested_mode"] == "tiny_live"
    assert payload["resulting_mode"] == "tiny_live"
    assert payload["config_written"] is False
    assert payload["lane_mode_intent_state"] == TINY_LIVE_LANE_WAITING_FOR_CONDITIONS
    assert payload["lane_status_after_change"]["status"] == "LANE_BLOCKED"
    assert payload["global_gate_status"]["status"] == SENTINEL_STATUS
    assert _read_config(config_path)["lanes"][1]["mode"] == "paper"


def test_apply_wrong_confirmation_rejects_and_writes_no_config(monkeypatch: Any, tmp_path: Path) -> None:
    _block_heavy_global_gate(monkeypatch)
    config_path = _write_config(tmp_path)
    before = _read_config(config_path)

    payload = _command(
        config_path,
        tmp_path,
        lane_key=LANE_13M,
        apply=True,
        confirm_lane_change="wrong",
    )

    assert payload["status"] == LANE_COMMAND_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["config_written"] is False
    assert _read_config(config_path) == before
    assert not (tmp_path / "logs" / "lane_control_commands.ndjson").exists()


def test_apply_correct_confirmation_writes_only_lane_mode(monkeypatch: Any, tmp_path: Path) -> None:
    _block_heavy_global_gate(monkeypatch)
    config_path = _write_config(tmp_path)
    before = _read_config(config_path)

    payload = _command(
        config_path,
        tmp_path,
        lane_key=LANE_13M,
        apply=True,
        confirm_lane_change=CONFIRM_LANE_CHANGE_PHRASE,
    )
    after = _read_config(config_path)

    assert payload["status"] == LANE_COMMAND_APPLIED
    assert payload["config_written"] is True
    assert payload["lane_mode_intent_state"] == TINY_LIVE_LANE_WAITING_FOR_CONDITIONS
    assert after["lanes"][0]["mode"] == "tiny_live"
    for index, lane in enumerate(before["lanes"]):
        for key, value in lane.items():
            if index == 0 and key == "mode":
                continue
            assert after["lanes"][index][key] == value
    assert after["notes"] == before["notes"]
    assert after["schema_version"] == before["schema_version"]
    assert after["default_mode"] == before["default_mode"]


def test_apply_does_not_mutate_env_global_flags_or_network_boundaries(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    _block_heavy_global_gate(monkeypatch)
    config_path = _write_config(tmp_path)
    env_before = dict(os.environ)

    def fail_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network/order boundary must not be called")

    monkeypatch.setattr("socket.create_connection", fail_network)

    payload = _command(
        config_path,
        tmp_path,
        lane_key=LANE_44M,
        apply=True,
        confirm_lane_change=CONFIRM_LANE_CHANGE_PHRASE,
    )

    assert payload["status"] == LANE_COMMAND_APPLIED
    assert dict(os.environ) == env_before
    assert payload["safety"] == {
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "order_payload_created": False,
        "network_allowed": False,
        "secrets_shown": False,
        "env_mutated": False,
        "global_live_flags_changed": False,
    }
    assert payload["global_gate_status"]["execution_enabled"] is False
    assert payload["global_gate_status"]["allow_live_orders"] is False
    assert payload["global_gate_status"]["global_kill_switch_active"] is True
    assert payload["lane_status_after_change"]["status"] != "LIVE_ORDER_READY"
    assert payload["lane_status_after_change"]["status"] != "FIRST_LIVE_ACTIVATION_READY"
    assert payload["safety"]["order_placed"] is False


def _block_heavy_global_gate(monkeypatch: Any) -> None:
    def fail_gate(*args: object, **kwargs: object) -> None:
        raise AssertionError("heavy first-live activation gate must not be called")

    monkeypatch.setattr("src.app.hammer_radar.operator.lane_control._load_global_gate", fail_gate)
    monkeypatch.setattr(
        "src.app.hammer_radar.operator.first_live_activation_gate.build_first_live_activation_gate",
        fail_gate,
    )


def _command(
    config_path: Path,
    tmp_path: Path,
    *,
    lane_key: str,
    apply: bool = False,
    confirm_lane_change: str | None = None,
) -> dict[str, Any]:
    return apply_lane_command(
        action="set-mode",
        lane_key=lane_key,
        mode="tiny_live",
        apply=apply,
        confirm_lane_change=confirm_lane_change,
        request_tiny_live=True,
        config_path=config_path,
        log_dir=tmp_path / "logs",
        live_eligibility_matrix=_matrix(),
    )


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "lane_controls.json"
    path.write_text(json.dumps(_config(), indent=2) + "\n", encoding="utf-8")
    return path


def _read_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _config() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "default_mode": "disabled",
        "notes": [
            "R122 lane controls express operator intent only.",
            "This config does not create order payloads, enable live execution, or bypass global live gates.",
        ],
        "lanes": [
            {
                "symbol": "BTCUSDT",
                "timeframe": "13m",
                "direction": "long",
                "entry_mode": "ladder_close_50_618",
                "mode": "armed_dry_run",
                "max_daily_trades": 1,
                "max_daily_loss_pct": 0.25,
                "freshness_seconds": 120,
                "cooldown_after_loss_minutes": 120,
                "require_protective_orders": True,
            },
            {
                "symbol": "BTCUSDT",
                "timeframe": "44m",
                "direction": "long",
                "entry_mode": "ladder_close_50_618",
                "mode": "paper",
                "max_daily_trades": 1,
                "max_daily_loss_pct": 0.25,
                "freshness_seconds": 300,
                "cooldown_after_loss_minutes": 180,
                "require_protective_orders": True,
            },
        ],
    }
