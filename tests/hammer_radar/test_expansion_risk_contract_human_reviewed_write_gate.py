from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.expansion_risk_contract_human_reviewed_write_gate import (
    CONFIRMATION_PHRASE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    WRITE_GATE_REJECTED_BAD_CONFIRMATION,
    WRITE_GATE_WRITTEN,
    build_expansion_risk_contract_human_reviewed_write_gate,
)
from src.app.hammer_radar.operator.expansion_risk_contract_write_gate_preview import (
    build_expansion_risk_contract_write_gate_preview,
)

NOW = datetime(2026, 6, 25, 9, 0, tzinfo=UTC)
BASELINE = "BTCUSDT|44m|long|ladder_close_50_618"
PRIMARY = [
    "BTCUSDT|44m|short|ladder_382_50_618",
    "BTCUSDT|44m|short|ladder_close_50_618",
    "BTCUSDT|55m|long|ladder_close_50_618",
]
SECONDARY = [
    "BTCUSDT|44m|short|ladder_22_44_22",
    "BTCUSDT|44m|long|ladder_382_50_618",
    "BTCUSDT|55m|long|market_close",
    "BTCUSDT|88m|long|ladder_382_50_618",
]
ALL_R308_LANES = [BASELINE, *PRIMARY, *SECONDARY]


def test_default_run_is_preview_only_and_does_not_write(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    risk_path = _write_risk_config(tmp_path / "tiny_live_risk_contracts.json")
    before = risk_path.read_text(encoding="utf-8")

    payload = build_expansion_risk_contract_human_reviewed_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["event_type"] == EVENT_TYPE
    assert payload["apply_requested"] is False
    assert payload["preview_only"] is True
    assert payload["confirmation_phrase_matched"] is False
    assert payload["config_written"] is False
    assert payload["risk_contract_config_mutated"] is False
    assert payload["would_add_lane_keys"] == ALL_R308_LANES
    assert payload["proposed_contract_count"] == 8
    assert risk_path.read_text(encoding="utf-8") == before
    assert (log_dir / LEDGER_FILENAME).exists()


def test_wrong_or_missing_confirmation_phrase_blocks_write(tmp_path: Path) -> None:
    risk_path = _write_risk_config(tmp_path / "tiny_live_risk_contracts.json")
    before = risk_path.read_text(encoding="utf-8")

    missing = build_expansion_risk_contract_human_reviewed_write_gate(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=risk_path,
        apply=True,
        now=NOW,
    )
    wrong = build_expansion_risk_contract_human_reviewed_write_gate(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=risk_path,
        apply=True,
        confirmation="wrong",
        now=NOW,
    )

    assert missing["status"] == WRITE_GATE_REJECTED_BAD_CONFIRMATION
    assert wrong["status"] == WRITE_GATE_REJECTED_BAD_CONFIRMATION
    assert missing["confirmation_phrase_matched"] is False
    assert wrong["confirmation_phrase_matched"] is False
    assert missing["config_written"] is False
    assert wrong["config_written"] is False
    assert risk_path.read_text(encoding="utf-8") == before


def test_apply_mode_with_exact_phrase_writes_only_to_temp_config_path(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    risk_path = _write_risk_config(tmp_path / "tiny_live_risk_contracts.json")
    arming_path = _write_arming_state(tmp_path / "autonomous_arming_state.json")
    repo_config = Path("configs/hammer_radar/tiny_live_risk_contracts.json")
    repo_config_before = repo_config.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")
    before_env = dict(os.environ)

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = build_expansion_risk_contract_human_reviewed_write_gate(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            apply=True,
            confirmation=CONFIRMATION_PHRASE,
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    signed_order.assert_not_called()
    assert dict(os.environ) == before_env
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert repo_config.read_text(encoding="utf-8") == repo_config_before
    assert payload["status"] == WRITE_GATE_WRITTEN
    assert payload["config_written"] is True
    assert payload["risk_contract_config_mutated"] is True
    assert payload["confirmation_phrase_matched"] is True
    assert payload["added_lane_keys"] == ALL_R308_LANES
    assert payload["backup_created"] is True
    assert Path(payload["backup_path"]).exists()
    assert payload["post_write_validation"]["all_added_rows_found"] is True
    assert payload["post_write_validation"]["all_added_rows_valid"] is True


def test_existing_rows_are_not_modified_or_deleted_and_missing_exact_rows_are_appended(tmp_path: Path) -> None:
    existing_lane = PRIMARY[0]
    risk_path = _write_risk_config(
        tmp_path / "tiny_live_risk_contracts.json",
        existing_lanes=["BTCUSDT|8m|short|ladder_close_50_618", existing_lane],
    )
    before = json.loads(risk_path.read_text(encoding="utf-8"))
    original_first = dict(before["risk_contracts"][0])
    original_existing = dict(before["risk_contracts"][1])

    payload = build_expansion_risk_contract_human_reviewed_write_gate(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=risk_path,
        apply=True,
        confirmation=CONFIRMATION_PHRASE,
        now=NOW,
    )
    after = json.loads(risk_path.read_text(encoding="utf-8"))

    assert payload["skipped_existing_lane_keys"] == [existing_lane]
    assert existing_lane not in payload["added_lane_keys"]
    assert after["risk_contracts"][0] == original_first
    assert after["risk_contracts"][1] == original_existing
    assert len(after["risk_contracts"]) == len(before["risk_contracts"]) + 7
    after_keys = {_lane_key(row) for row in after["risk_contracts"]}
    assert set(ALL_R308_LANES).issubset(after_keys)
    assert "BTCUSDT|8m|short|ladder_close_50_618" in after_keys


def test_new_rows_keep_live_flags_false_and_no_secrets_shown(tmp_path: Path) -> None:
    risk_path = _write_risk_config(tmp_path / "tiny_live_risk_contracts.json")
    payload = build_expansion_risk_contract_human_reviewed_write_gate(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=risk_path,
        apply=True,
        confirmation=CONFIRMATION_PHRASE,
        now=NOW,
    )
    config = json.loads(risk_path.read_text(encoding="utf-8"))
    rows = [row for row in config["risk_contracts"] if _lane_key(row) in ALL_R308_LANES]

    assert len(rows) == 8
    for row in rows:
        assert row["live_execution_enabled"] is False
        assert row["allow_live_orders"] is False
    for key in (
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "submit_allowed",
        "final_command_available",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "leverage_change_called",
        "margin_change_called",
        "secrets_shown",
        "autonomous_arming_state_changed",
        "global_live_flags_changed",
        "env_written",
        "env_mutated",
    ):
        assert payload[key] is False
    assert payload["real_order_forbidden"] is True
    assert payload["paper_live_separation_intact"] is True


def test_inspect_route_works(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "expansion-risk-contract-human-reviewed-write-gate",
        ],
        cwd=root,
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["apply_requested"] is False
    assert payload["config_written"] is False


def test_operator_script_exists_and_only_previews(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["bash", "scripts/hammer_print_r309_expansion_risk_contract_human_reviewed_write_gate.sh"],
        cwd=root,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "R309 HUMAN-REVIEWED RISK CONTRACT WRITE GATE" in result.stdout
    assert "apply_requested: False" in result.stdout
    assert "confirmation_phrase_matched: False" in result.stdout
    assert "config_written: False" in result.stdout
    assert "--apply" in result.stdout


def test_r308_compatibility_remains_intact(tmp_path: Path) -> None:
    risk_path = _write_risk_config(tmp_path / "tiny_live_risk_contracts.json")
    r308 = build_expansion_risk_contract_write_gate_preview(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=risk_path,
        write=False,
        now=NOW,
    )
    r309 = build_expansion_risk_contract_human_reviewed_write_gate(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=risk_path,
        write_ledger=False,
        now=NOW,
    )

    assert r308["proposed_contract_count"] == r309["proposed_contract_count"] == 8
    assert [row["proposed_contract"] for row in r308["proposed_contract_rows"]] == [
        row["proposed_contract"] for row in r309["proposed_contract_rows"]
    ]
    assert r308["config_written"] is False
    assert r309["config_written"] is False


def _write_risk_config(path: Path, *, existing_lanes: list[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "funding_config": {
            "funding_config_present": True,
            "funding_check_mode": "LOCAL_CONFIG_ONLY_NO_NETWORK",
            "max_margin_usdt": 44.0,
            "max_loss_usdt": 4.44,
        },
        "risk_contracts": [_contract(lane) for lane in existing_lanes or []],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_arming_state(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "armed_lane_key": BASELINE,
                "allowed_lane_keys": [BASELINE],
                "auto_execute_mode": "dry_run_only",
                "live_execution_enabled": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _contract(lane_key: str) -> dict[str, object]:
    symbol, timeframe, direction, entry_mode = lane_key.split("|")
    return {
        "official_lane_key": lane_key,
        "contract_version": "tiny_live_percentage_risk_contract_v2",
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "tiny_live_contract_mode": "explicit_notional_cap_with_leverage",
        "max_position_notional_usdt": 80,
        "max_notional_usdt": 80,
        "leverage": 10,
        "margin_budget_usdt": 8,
        "max_margin_usdt": 8,
        "max_loss_usdt": 4.44,
        "margin_mode": "isolated",
        "protective_orders_required": True,
        "protective_stop_required": True,
        "take_profit_required": True,
        "live_execution_enabled": False,
        "allow_live_orders": False,
        "live_authorized": False,
    }


def _lane_key(row: dict[str, object]) -> str:
    return str(row.get("official_lane_key") or "|".join(str(row.get(key) or "") for key in ("symbol", "timeframe", "direction", "entry_mode")))
