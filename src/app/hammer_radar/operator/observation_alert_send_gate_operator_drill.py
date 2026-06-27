"""R317 synthetic operator drill for the R316 observation alert send gate.

The drill builds synthetic R314 health-panel payloads, passes them through the
R315 preview and R316 send gate, and records only mock/no-real-send outcomes.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.multi_lane_observation_alert_send_gate import (
    CONFIRMATION_PHRASE,
    SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED,
    SEND_GATE_BLOCKED_NO_ALERT_REQUIRED,
    SEND_GATE_MOCK_SENT,
    build_multi_lane_observation_alert_send_gate,
)
from src.app.hammer_radar.operator.multi_lane_observation_alerting_preview import (
    CRITICAL_PREVIEW_NO_SEND,
    INFO_PREVIEW_NO_SEND,
    SAFETY as R315_SAFETY,
    WARNING_PREVIEW_NO_SEND,
    build_multi_lane_observation_alerting_preview,
)
from src.app.hammer_radar.operator.multi_lane_observation_health_panel import (
    HEALTH_BLOCKED,
    HEALTH_DEGRADED,
    HEALTH_OK,
    SAFETY as R314_SAFETY,
)

EVENT_TYPE = "R317_OBSERVATION_ALERT_SEND_GATE_OPERATOR_DRILL"
CREATED_BY_PHASE = "R317_OBSERVATION_ALERT_SEND_GATE_OPERATOR_DRILL"
LEDGER_FILENAME = "observation_alert_send_gate_operator_drill.ndjson"

DRILL_PASSED = "OPERATOR_DRILL_PASSED"
DRILL_FAILED = "OPERATOR_DRILL_FAILED"

SCENARIO_HEALTHY = "healthy"
SCENARIO_STALE_OBSERVATION = "stale_observation"
SCENARIO_FINAL_SAFETY_VIOLATION = "final_safety_violation"
SCENARIO_ALL = "all"
SCENARIOS = (SCENARIO_HEALTHY, SCENARIO_STALE_OBSERVATION, SCENARIO_FINAL_SAFETY_VIOLATION)

RECOMMENDED_R318_CLEAN = "R318 Real Telegram Alert Send Gate Preview"
RECOMMENDED_R318_REPAIR = "R318 Operator Drill Repair"

SAFETY = {
    **R314_SAFETY,
    "real_telegram_send_called": False,
    "real_telegram_message_sent": False,
}


def build_observation_alert_send_gate_operator_drill(
    *,
    log_dir: str | Path | None = None,
    scenario: str = SCENARIO_ALL,
    confirmation: str | None = None,
    max_age_seconds: int = 180,
    no_write: bool = False,
    write: bool | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    should_write = (not no_write) if write is None else bool(write)
    scenario_names = list(SCENARIOS if scenario == SCENARIO_ALL else (scenario,))

    results = [
        run_synthetic_scenario(
            scenario_name=name,
            log_dir=resolved_log_dir,
            confirmation=confirmation,
            max_age_seconds=max_age_seconds,
            now=generated_at,
        )
        for name in scenario_names
    ]
    blockers = _drill_blockers(results, scenario_names)
    passed = not blockers and all(result["passed"] is True for result in results)
    safety = dict(SAFETY)
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "drill_id": f"r317_observation_alert_send_gate_operator_drill_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ledger_path": str(records_path(resolved_log_dir)),
        "drill_status": DRILL_PASSED if passed else DRILL_FAILED,
        "drill_blockers": blockers,
        "scenarios_run": scenario_names,
        "scenario_results": results,
        "healthy_no_send_passed": _scenario_passed(results, SCENARIO_HEALTHY),
        "stale_alert_mock_send_gate_passed": _scenario_passed(results, SCENARIO_STALE_OBSERVATION),
        "final_safety_critical_mock_send_gate_passed": _scenario_passed(
            results, SCENARIO_FINAL_SAFETY_VIOLATION
        ),
        "exact_confirmation_required_passed": all(
            result["exact_confirmation_required_passed"] is True for result in results
        ),
        "no_real_telegram_passed": all(result["no_real_telegram_passed"] is True for result in results),
        "no_mutation_passed": all(result["no_mutation_passed"] is True for result in results),
        "recommended_next_operator_move": (
            "prepare_real_telegram_alert_send_gate_preview" if passed else "repair_operator_drill_blockers"
        ),
        "recommended_r318_path": RECOMMENDED_R318_CLEAN if passed else RECOMMENDED_R318_REPAIR,
        "synthetic_scenario": True,
        "synthetic_inputs_used": True,
        "real_runtime_mutated": False,
        "telegram_sender_mode": "mock",
        "telegram_send_called": any(result["telegram_send_called"] for result in results),
        "telegram_message_sent": any(result["telegram_message_sent"] for result in results),
        "real_telegram_send_called": False,
        "real_telegram_message_sent": False,
        "safety": safety,
        **safety,
    }
    safe_payload = _sanitize(payload)
    if should_write:
        append_record(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def run_synthetic_scenario(
    *,
    scenario_name: str,
    log_dir: str | Path,
    confirmation: str | None,
    max_age_seconds: int,
    now: datetime,
) -> dict[str, Any]:
    health = build_synthetic_health_panel(
        scenario_name=scenario_name,
        now=now,
        max_age_seconds=max_age_seconds,
    )
    preview = build_multi_lane_observation_alerting_preview(
        log_dir=log_dir,
        max_age_seconds=max_age_seconds,
        write=False,
        now=now,
        health_panel=health,
    )
    preview["dedup_key"] = f"r317:{scenario_name}:{preview.get('alert_severity')}"
    expected_alert_required = scenario_name != SCENARIO_HEALTHY
    expected_statuses = _expected_send_gate_statuses(scenario_name)
    attempts = _gate_attempts(
        scenario_name=scenario_name,
        log_dir=log_dir,
        preview=preview,
        confirmation=confirmation,
        now=now,
    )
    observed_statuses = [str(attempt["send_gate_status"]) for attempt in attempts]
    exact_attempt = attempts[-1]
    blockers = _scenario_blockers(
        scenario_name=scenario_name,
        expected_alert_required=expected_alert_required,
        preview=preview,
        attempts=attempts,
        expected_statuses=expected_statuses,
    )
    passed = not blockers
    telegram_send_called = any(attempt["telegram_send_called"] is True for attempt in attempts)
    telegram_message_sent = any(attempt["telegram_message_sent"] is True for attempt in attempts)
    return {
        "scenario_name": scenario_name,
        "synthetic_scenario": True,
        "synthetic_inputs_used": True,
        "real_runtime_mutated": False,
        "expected_alert_required": expected_alert_required,
        "observed_alert_required": bool(preview.get("alert_required")),
        "observed_alert_severity": str(preview.get("alert_severity") or ""),
        "observed_alert_reasons": list(preview.get("alert_reasons") or []),
        "expected_send_gate_statuses": expected_statuses,
        "observed_send_gate_status": exact_attempt["send_gate_status"],
        "observed_send_gate_statuses": observed_statuses,
        "confirmation_required": True,
        "confirmation_matched": bool(exact_attempt.get("confirmation_phrase_matched")),
        "operator_confirmation_matched": str(confirmation or "") == CONFIRMATION_PHRASE,
        "telegram_sender_mode": "mock",
        "telegram_send_called": telegram_send_called,
        "telegram_message_sent": telegram_message_sent,
        "real_telegram_send_called": False,
        "real_telegram_message_sent": False,
        "passed": passed,
        "result_status": "PASS" if passed else "FAIL",
        "blockers": blockers,
        "gate_attempts": attempts,
        "source_alert_preview": preview,
        "exact_confirmation_required_passed": _confirmation_required_passed(scenario_name, attempts),
        "no_real_telegram_passed": all(
            attempt["real_telegram_send_called"] is False and attempt["real_telegram_message_sent"] is False
            for attempt in attempts
        ),
        "no_mutation_passed": _no_mutation_passed(attempts),
        "safety": dict(SAFETY),
        **SAFETY,
    }


def build_synthetic_health_panel(
    *,
    scenario_name: str,
    now: datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    stale_age = max_age_seconds + 60
    health: dict[str, Any] = {
        "event_type": "R314_MULTI_LANE_OBSERVATION_HEALTH_PANEL",
        "created_by_phase": CREATED_BY_PHASE,
        "generated_at": now.isoformat(),
        "health_status": HEALTH_OK,
        "health_blockers": [],
        "timer_summary": {
            "timer_installed": True,
            "timer_enabled": True,
            "timer_active": True,
            "service_last_exit_status": "0",
            "last_tick_seen": now.isoformat(),
            "last_tick_age_seconds": 30,
            "last_tick_recent": True,
            "systemctl_read_only": True,
        },
        "lane_summary": {
            "baseline_lane": "BTCUSDT|44m|long|ladder_close_50_618",
            "primary_observed_lanes": ["BTCUSDT|44m|long|ladder_close_50_618"],
            "secondary_watch_only_lanes": [],
            "primary_observed_count": 1,
            "secondary_watch_only_count": 0,
            "all_primary_contracts_valid": True,
            "all_primary_observation_status_ok": True,
            "current_candidate_seen": False,
            "current_candidate_lane_key": None,
            "matching_observed_lane_keys": [],
            "candidate_freshness_status": "FRESH_TRIGGER_WAIT",
        },
        "final_live_safety": {
            "final_gate_status": "SYNTHETIC_FINAL_GATE_SAFE",
            "final_gate_blockers": [],
            "real_order_forbidden": True,
            "submit_allowed": False,
            "final_command_available": False,
            "armed_lane_key": "BTCUSDT|44m|long|ladder_close_50_618",
            "timer_health_status": "TIMER_HEALTH_ACTIVE",
            "timer_active": True,
        },
        "paper_refresh_summary": {
            "paper_refresh_health_status": "PAPER_REFRESH_HEALTHY",
            "last_failed_tasks": [],
            "degraded_non_critical_accepted": False,
            "fatal": False,
            "healthy": True,
        },
        "synthetic_scenario": True,
        "synthetic_inputs_used": True,
        "real_runtime_mutated": False,
        "safety": dict(R315_SAFETY),
        **R315_SAFETY,
    }
    if scenario_name == SCENARIO_STALE_OBSERVATION:
        health["health_status"] = HEALTH_DEGRADED
        health["health_blockers"] = ["stale_observation_tick"]
        health["timer_summary"] = {
            **_mapping(health["timer_summary"]),
            "last_tick_age_seconds": stale_age,
            "last_tick_recent": False,
        }
    elif scenario_name == SCENARIO_FINAL_SAFETY_VIOLATION:
        health["health_status"] = HEALTH_BLOCKED
        health["health_blockers"] = ["submit_allowed_unexpected", "final_command_available_unexpected"]
        health["final_live_safety"] = {
            **_mapping(health["final_live_safety"]),
            "final_gate_status": "SYNTHETIC_FINAL_GATE_UNSAFE",
            "final_gate_blockers": ["synthetic_submit_allowed", "synthetic_final_command_available"],
            "real_order_forbidden": False,
            "submit_allowed": True,
            "final_command_available": True,
        }
    elif scenario_name != SCENARIO_HEALTHY:
        raise ValueError(f"unsupported synthetic scenario: {scenario_name}")
    return _sanitize(health)


def load_observation_alert_send_gate_operator_drill_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(records_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def append_record(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = records_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_operator_drill_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), indent=2, sort_keys=True)


def format_operator_drill_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R317 OBSERVATION ALERT SEND GATE OPERATOR DRILL",
        "",
        "DRILL STATUS",
        f"drill_status: {payload.get('drill_status')}",
        f"drill_blockers: {_join(payload.get('drill_blockers'))}",
        "",
        "SCENARIOS RUN",
        f"scenarios_run: {_join(payload.get('scenarios_run'))}",
        "",
        "HEALTHY NO-SEND RESULT",
        _format_scenario_line(payload, SCENARIO_HEALTHY),
        "",
        "STALE OBSERVATION RESULT",
        _format_scenario_line(payload, SCENARIO_STALE_OBSERVATION),
        "",
        "FINAL SAFETY VIOLATION RESULT",
        _format_scenario_line(payload, SCENARIO_FINAL_SAFETY_VIOLATION),
        "",
        "CONFIRMATION GATE RESULT",
        f"exact_confirmation_required_passed: {payload.get('exact_confirmation_required_passed')}",
        "",
        "MOCK/REAL SEND FLAGS",
        f"telegram_sender_mode: {payload.get('telegram_sender_mode')}",
        f"telegram_send_called: {payload.get('telegram_send_called')}",
        f"telegram_message_sent: {payload.get('telegram_message_sent')}",
        f"real_telegram_send_called: {payload.get('real_telegram_send_called')}",
        f"real_telegram_message_sent: {payload.get('real_telegram_message_sent')}",
        "",
        "SAFETY FLAGS",
    ]
    for key in SAFETY:
        lines.append(f"{key}: {payload.get(key)}")
    lines.extend(
        [
            f"synthetic_scenario: {payload.get('synthetic_scenario')}",
            f"synthetic_inputs_used: {payload.get('synthetic_inputs_used')}",
            f"real_runtime_mutated: {payload.get('real_runtime_mutated')}",
            "",
            "RECOMMENDED NEXT PHASE",
            str(payload.get("recommended_r318_path")),
        ]
    )
    return "\n".join(lines)


def _gate_attempts(
    *,
    scenario_name: str,
    log_dir: str | Path,
    preview: Mapping[str, Any],
    confirmation: str | None,
    now: datetime,
) -> list[dict[str, Any]]:
    if scenario_name == SCENARIO_HEALTHY:
        attempts = [("healthy_exact_confirmation_no_send", CONFIRMATION_PHRASE)]
    else:
        attempts = [
            ("missing_confirmation_blocks", None),
            ("wrong_confirmation_blocks", "WRONG CONFIRMATION"),
            ("exact_confirmation_mock_send", CONFIRMATION_PHRASE),
        ]
        if confirmation is not None and confirmation != CONFIRMATION_PHRASE:
            attempts.insert(2, ("operator_supplied_confirmation_blocks", confirmation))
    results: list[dict[str, Any]] = []
    for attempt_name, phrase in attempts:
        gate = build_multi_lane_observation_alert_send_gate(
            log_dir=log_dir,
            apply=True,
            confirmation=phrase,
            telegram_sender_mode="mock",
            no_write=True,
            write=False,
            now=now,
            alert_preview=deepcopy(dict(preview)),
        )
        results.append(
            {
                "attempt_name": attempt_name,
                "send_gate_status": gate.get("send_gate_status"),
                "confirmation_phrase_matched": gate.get("confirmation_phrase_matched"),
                "telegram_sender_mode": gate.get("telegram_sender_mode"),
                "telegram_send_called": gate.get("telegram_send_called"),
                "telegram_message_sent": gate.get("telegram_message_sent"),
                "real_telegram_send_called": gate.get("real_telegram_send_called"),
                "real_telegram_message_sent": gate.get("real_telegram_message_sent"),
                "send_blockers": list(gate.get("send_blockers") or []),
                "submit_allowed": gate.get("submit_allowed"),
                "final_command_available": gate.get("final_command_available"),
                "order_placed": gate.get("order_placed"),
                "real_order_placed": gate.get("real_order_placed"),
                "execution_attempted": gate.get("execution_attempted"),
                "binance_order_endpoint_called": gate.get("binance_order_endpoint_called"),
                "binance_test_order_endpoint_called": gate.get("binance_test_order_endpoint_called"),
                "config_written": gate.get("config_written"),
                "risk_contract_config_mutated": gate.get("risk_contract_config_mutated"),
                "autonomous_arming_state_changed": gate.get("autonomous_arming_state_changed"),
                "systemd_unit_mutated": gate.get("systemd_unit_mutated"),
                "scheduler_started": gate.get("scheduler_started"),
            }
        )
    return results


def _expected_send_gate_statuses(scenario_name: str) -> list[str]:
    if scenario_name == SCENARIO_HEALTHY:
        return [SEND_GATE_BLOCKED_NO_ALERT_REQUIRED]
    return [SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED, SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED, SEND_GATE_MOCK_SENT]


def _scenario_blockers(
    *,
    scenario_name: str,
    expected_alert_required: bool,
    preview: Mapping[str, Any],
    attempts: Sequence[Mapping[str, Any]],
    expected_statuses: Sequence[str],
) -> list[str]:
    blockers: list[str] = []
    if bool(preview.get("alert_required")) is not expected_alert_required:
        blockers.append("alert_required_mismatch")
    severity = str(preview.get("alert_severity") or "")
    if scenario_name == SCENARIO_HEALTHY and severity != INFO_PREVIEW_NO_SEND:
        blockers.append("healthy_severity_not_info")
    if scenario_name == SCENARIO_STALE_OBSERVATION and severity not in {
        WARNING_PREVIEW_NO_SEND,
        CRITICAL_PREVIEW_NO_SEND,
    }:
        blockers.append("stale_severity_not_actionable")
    if scenario_name == SCENARIO_FINAL_SAFETY_VIOLATION and severity != CRITICAL_PREVIEW_NO_SEND:
        blockers.append("final_safety_severity_not_critical")
    observed_statuses = [str(attempt.get("send_gate_status")) for attempt in attempts[: len(expected_statuses)]]
    if observed_statuses != list(expected_statuses):
        blockers.append("send_gate_status_sequence_mismatch")
    if not _confirmation_required_passed(scenario_name, attempts):
        blockers.append("confirmation_gate_not_proven")
    if any(attempt.get("real_telegram_send_called") is not False for attempt in attempts):
        blockers.append("real_telegram_send_called")
    if any(attempt.get("real_telegram_message_sent") is not False for attempt in attempts):
        blockers.append("real_telegram_message_sent")
    if not _no_mutation_passed(attempts):
        blockers.append("mutation_flag_unexpected")
    return _dedupe(blockers)


def _confirmation_required_passed(scenario_name: str, attempts: Sequence[Mapping[str, Any]]) -> bool:
    if scenario_name == SCENARIO_HEALTHY:
        return attempts[0].get("send_gate_status") == SEND_GATE_BLOCKED_NO_ALERT_REQUIRED
    blocked = [
        attempt
        for attempt in attempts
        if str(attempt.get("attempt_name", "")).endswith("_blocks")
        or attempt.get("attempt_name") in {"missing_confirmation_blocks", "wrong_confirmation_blocks"}
    ]
    exact = attempts[-1]
    return (
        all(attempt.get("send_gate_status") == SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED for attempt in blocked)
        and exact.get("send_gate_status") == SEND_GATE_MOCK_SENT
        and exact.get("confirmation_phrase_matched") is True
    )


def _no_mutation_passed(attempts: Sequence[Mapping[str, Any]]) -> bool:
    false_fields = (
        "config_written",
        "risk_contract_config_mutated",
        "autonomous_arming_state_changed",
        "systemd_unit_mutated",
        "scheduler_started",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "submit_allowed",
        "final_command_available",
    )
    return all(all(attempt.get(field) is False for field in false_fields) for attempt in attempts)


def _drill_blockers(results: Sequence[Mapping[str, Any]], scenario_names: Sequence[str]) -> list[str]:
    blockers: list[str] = []
    missing = set(scenario_names) - {str(result.get("scenario_name")) for result in results}
    if missing:
        blockers.append("missing_scenario_results")
    for result in results:
        if result.get("passed") is not True:
            blockers.append(f"{result.get('scenario_name')}_failed")
    return _dedupe(blockers)


def _scenario_passed(results: Sequence[Mapping[str, Any]], scenario_name: str) -> bool:
    for result in results:
        if result.get("scenario_name") == scenario_name:
            return result.get("passed") is True
    return False


def _format_scenario_line(payload: Mapping[str, Any], scenario_name: str) -> str:
    for result in payload.get("scenario_results") or []:
        if isinstance(result, Mapping) and result.get("scenario_name") == scenario_name:
            return (
                f"{result.get('result_status')} | alert_required={result.get('observed_alert_required')} | "
                f"severity={result.get('observed_alert_severity')} | "
                f"send_gate_status={result.get('observed_send_gate_status')} | "
                f"telegram_send_called={result.get('telegram_send_called')} | "
                f"real_telegram_send_called={result.get('real_telegram_send_called')}"
            )
    return "not_run"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _join(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value) if value else "none"
    return str(value) if value not in (None, "") else "none"


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value)
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.app.hammer_radar.operator.observation_alert_send_gate_operator_drill"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--scenario", choices=(*SCENARIOS, SCENARIO_ALL), default=SCENARIO_ALL)
    parser.add_argument("--confirmation", default=None)
    parser.add_argument("--max-age-seconds", type=int, default=180)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    payload = build_observation_alert_send_gate_operator_drill(
        log_dir=args.log_dir,
        scenario=args.scenario,
        confirmation=args.confirmation,
        max_age_seconds=args.max_age_seconds,
        no_write=args.no_write,
    )
    if args.json and not args.text:
        print(format_operator_drill_json(payload))
    else:
        print(format_operator_drill_text(payload))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint.
    raise SystemExit(main())
