from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.signal_origin_registry import (
    CONFIRM_SIGNAL_ORIGIN_REGISTRY_RECORDING_PHRASE,
    LEDGER_FILENAME,
    REGISTRY_ONLY,
    SIGNAL_ORIGIN_REGISTRY_RECORDED,
    SIGNAL_ORIGIN_REGISTRY_REJECTED,
    build_signal_origin_feed_summary,
    build_signal_origin_registry,
    build_signal_origin_registry_preview,
    infer_signal_origin_from_record,
    load_signal_origin_registry_records,
    normalize_signal_origin,
    tag_signal_records_with_origin,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    payload = build_signal_origin_registry_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_registry_requested"] is False
    assert payload["registry_recorded"] is False
    assert payload["registry_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    payload = build_signal_origin_registry_preview(
        log_dir=tmp_path / "logs",
        record_registry=True,
        confirm_signal_origin_registry="wrong",
        now=NOW,
    )

    assert payload["status"] == SIGNAL_ORIGIN_REGISTRY_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["registry_recorded"] is False
    assert load_signal_origin_registry_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    before_env = dict(os.environ)

    payload = build_signal_origin_registry_preview(
        log_dir=tmp_path / "logs",
        record_registry=True,
        confirm_signal_origin_registry=CONFIRM_SIGNAL_ORIGIN_REGISTRY_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_signal_origin_registry_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == SIGNAL_ORIGIN_REGISTRY_RECORDED
    assert payload["registry_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "SIGNAL_ORIGIN_REGISTRY"
    assert before_env == dict(os.environ)


def test_registry_includes_required_origins_and_safety_flags() -> None:
    registry = build_signal_origin_registry()
    origins = {entry["signal_origin"]: entry for entry in registry}

    for origin in (
        "hammer_wick_reversal",
        "golden_pocket_rejection",
        "three_black_crows",
        "three_white_soldiers",
        "bearish_engulfing",
        "bullish_engulfing",
        "rsi_divergence_bearish",
        "rsi_divergence_bullish",
        "breakdown_retest",
        "breakout_retest",
        "exhaustion_wick",
        "unknown_or_unclassified",
    ):
        assert origin in origins
        assert origins[origin]["live_authorized"] is False
        assert origins[origin]["paper_only"] is True


def test_registry_only_origins_do_not_claim_detector_availability() -> None:
    registry = {entry["signal_origin"]: entry for entry in build_signal_origin_registry()}

    assert registry["three_black_crows"]["availability"] == REGISTRY_ONLY
    assert registry["three_black_crows"]["available_for_tagging"] is False
    assert registry["three_white_soldiers"]["availability"] == REGISTRY_ONLY
    assert registry["bearish_engulfing"]["availability"] == REGISTRY_ONLY
    assert registry["bullish_engulfing"]["availability"] == REGISTRY_ONLY


def test_unknown_fallback_and_normalize_aliases_work() -> None:
    assert normalize_signal_origin("hammer") == "hammer_wick_reversal"
    assert normalize_signal_origin("3_black_crows") == "three_black_crows"
    assert normalize_signal_origin("engulfing_bullish") == "bullish_engulfing"
    assert normalize_signal_origin("rsi_bear_div") == "rsi_divergence_bearish"
    assert normalize_signal_origin("not-a-real-origin") == "unknown_or_unclassified"
    assert infer_signal_origin_from_record({"symbol": "BTCUSDT"}) == "unknown_or_unclassified"


def test_infer_existing_hammer_and_golden_pocket_fields_when_available() -> None:
    assert infer_signal_origin_from_record({"hammer_strength": 91, "direction": "long"}) == "hammer_wick_reversal"
    assert infer_signal_origin_from_record({"entry_mode": "ladder_close_50_618", "direction": "short"}) == "golden_pocket_rejection"
    assert (
        infer_signal_origin_from_record({"lane_key": "BTCUSDT|8m|short|ladder_close_50_618"})
        == "golden_pocket_rejection"
    )


def test_infer_rsi_divergence_fields_when_available() -> None:
    assert (
        infer_signal_origin_from_record(
            {"divergence_confirmed": True, "divergence_type": "bearish", "direction": "short"}
        )
        == "rsi_divergence_bearish"
    )
    assert (
        infer_signal_origin_from_record(
            {"divergence": {"confirmed": True, "type": "bullish"}, "divergence_confirmed": True, "direction": "long"}
        )
        == "rsi_divergence_bullish"
    )


def test_feed_summary_tags_by_origin_and_lane(tmp_path: Path) -> None:
    records = [
        {"signal_id": "hammer", "symbol": "BTCUSDT", "timeframe": "4m", "direction": "long", "hammer_strength": 88},
        {
            "signal_id": "gp",
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
        },
        {"signal_id": "unknown", "symbol": "BTCUSDT", "timeframe": "13m", "direction": "short", "entry_mode": "market"},
    ]

    tagged = tag_signal_records_with_origin(records)
    summary = build_signal_origin_feed_summary(records)

    assert [row["signal_origin"] for row in tagged] == [
        "hammer_wick_reversal",
        "golden_pocket_rejection",
        "unknown_or_unclassified",
    ]
    assert summary["records_checked"] == 3
    assert summary["records_tagged"] == 3
    assert summary["by_origin"]["hammer_wick_reversal"] == 1
    assert summary["by_origin"]["golden_pocket_rejection"] == 1
    assert summary["by_origin"]["unknown_or_unclassified"] == 1
    assert summary["by_lane_and_origin"]["BTCUSDT|8m|short|ladder_close_50_618"]["golden_pocket_rejection"] == 1


def test_preview_reads_signals_and_harvester_feed_without_recording(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _append_json(log_dir / "signals.ndjson", {"signal_id": "s1", "symbol": "BTCUSDT", "timeframe": "4m", "direction": "long", "hammer_strength": 90})
    _append_json(
        log_dir / "multi_lane_paper_harvester.ndjson",
        {
            "captured_candidates": [
                {
                    "signal_id": "h1",
                    "symbol": "BTCUSDT",
                    "timeframe": "8m",
                    "direction": "short",
                    "entry_mode": "ladder_close_50_618",
                }
            ]
        },
    )

    payload = build_signal_origin_registry_preview(log_dir=log_dir, latest_signals=10, latest_harvest_records=10, now=NOW)

    assert payload["feed_summary"]["records_checked"] == 2
    assert payload["feed_summary"]["by_origin"]["hammer_wick_reversal"] == 1
    assert payload["feed_summary"]["by_origin"]["golden_pocket_rejection"] == 1
    assert payload["registry_recorded"] is False


def test_no_env_config_mutation_no_binance_calls_and_no_order_live_transfer_withdraw(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    config_path = tmp_path / "lane_controls.json"
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_signal_origin_registry_preview(log_dir=tmp_path / "logs", now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    safety = payload["safety"]
    for key, value in safety.items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "signal-origin-registry",
            "--latest-signals",
            "10",
            "--latest-harvest-records",
            "10",
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
    assert "registry" in payload
    assert "feed_summary" in payload
    assert "signal-origin-registry" in help_result.stdout


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
