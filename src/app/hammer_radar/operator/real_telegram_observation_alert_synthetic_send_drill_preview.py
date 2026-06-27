"""R320 synthetic real Telegram observation alert send drill preview.

This drill proves synthetic actionable alerts can reach the future real-send
eligibility boundary while keeping the R320 path preview-only. It never calls
Telegram, performs a mock send, mutates runtime state, submits orders, or calls
Binance endpoints.
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
from src.app.hammer_radar.operator.multi_lane_observation_alerting_preview import (
    CRITICAL_PREVIEW_NO_SEND,
    DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
    INFO_PREVIEW_NO_SEND,
    SAFETY as R315_SAFETY,
    WARNING_PREVIEW_NO_SEND,
    build_multi_lane_observation_alerting_preview,
)
from src.app.hammer_radar.operator.observation_alert_send_gate_operator_drill import (
    SCENARIO_FINAL_SAFETY_VIOLATION as R317_SCENARIO_FINAL_SAFETY_VIOLATION,
    SCENARIO_HEALTHY as R317_SCENARIO_HEALTHY,
    SCENARIO_STALE_OBSERVATION as R317_SCENARIO_STALE_OBSERVATION,
    build_synthetic_health_panel,
)
from src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview import (
    FUTURE_CONFIRMATION_PHRASE,
    build_real_telegram_observation_alert_send_preview,
)

EVENT_TYPE = "R320_REAL_TELEGRAM_OBSERVATION_ALERT_SYNTHETIC_SEND_DRILL_PREVIEW"
CREATED_BY_PHASE = "R320_REAL_TELEGRAM_OBSERVATION_ALERT_SYNTHETIC_SEND_DRILL_PREVIEW"
LEDGER_FILENAME = "real_telegram_observation_alert_synthetic_send_drill_preview.ndjson"

DRILL_PASSED = "REAL_TELEGRAM_SYNTHETIC_SEND_DRILL_PREVIEW_PASSED"
DRILL_FAILED = "REAL_TELEGRAM_SYNTHETIC_SEND_DRILL_PREVIEW_FAILED"

SCENARIO_HEALTHY = "healthy"
SCENARIO_SYNTHETIC_STALE_OBSERVATION = "synthetic_stale_observation"
SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION = "synthetic_final_safety_violation"
SCENARIO_ALL = "all"
SCENARIOS = (
    SCENARIO_HEALTHY,
    SCENARIO_SYNTHETIC_STALE_OBSERVATION,
    SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION,
)

RECOMMENDED_R321_APPLY_GATE = "R321 Human-Reviewed Real Telegram Synthetic Alert Send Apply Gate"
RECOMMENDED_R321_REPAIR = "R321 Real Telegram Synthetic Send Drill Preview Repair"

SAFETY = {
    **R315_SAFETY,
    "telegram_send_called": False,
    "telegram_message_sent": False,
    "real_telegram_send_called": False,
    "real_telegram_message_sent": False,
    "would_send_real_telegram_now": False,
    "real_send_preview_only": True,
}


def build_real_telegram_observation_alert_synthetic_send_drill_preview(
    *,
    log_dir: str | Path | None = None,
    scenario: str = SCENARIO_ALL,
    max_age_seconds: int = 180,
    rate_limit_window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
    no_write: bool = False,
    write: bool | None = None,
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
    env_file_path: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    should_write = (not no_write) if write is None else bool(write)
    scenario_names = list(SCENARIOS if scenario == SCENARIO_ALL else (scenario,))

    results = [
        run_synthetic_real_telegram_scenario(
            scenario_name=name,
            log_dir=resolved_log_dir,
            max_age_seconds=max_age_seconds,
            rate_limit_window_seconds=rate_limit_window_seconds,
            now=generated_at,
            env=env,
            env_file_path=env_file_path,
        )
        for name in scenario_names
    ]
    first_readiness = _first_readiness(results)
    credentials_ready = bool(first_readiness.get("telegram_config_valid_for_future_send"))
    blockers = _drill_blockers(results=results, scenario_names=scenario_names, credentials_ready=credentials_ready)
    passed = not blockers and all(result["pass"] is True for result in results)
    safety = dict(SAFETY)
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "drill_id": f"r320_real_telegram_synthetic_send_drill_preview_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ledger_path": str(records_path(resolved_log_dir)),
        "drill_status": DRILL_PASSED if passed else DRILL_FAILED,
        "drill_blockers": blockers,
        "telegram_config_readiness": first_readiness,
        "credentials_ready": credentials_ready,
        "real_send_available_for_future": credentials_ready,
        "scenarios_run": scenario_names,
        "scenario_results": results,
        "healthy_no_heartbeat_block_passed": _scenario_passed(results, SCENARIO_HEALTHY),
        "stale_future_real_send_eligibility_passed": _scenario_passed(
            results,
            SCENARIO_SYNTHETIC_STALE_OBSERVATION,
        ),
        "final_safety_future_real_send_eligibility_passed": _scenario_passed(
            results,
            SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION,
        ),
        "future_confirmation_inactive_passed": all(
            result["future_confirmation_phrase_active"] is False
            and result["future_confirmation_phrase_executable"] is False
            for result in results
        ),
        "future_confirmation_phrase_required": FUTURE_CONFIRMATION_PHRASE,
        "future_confirmation_phrase_active": False,
        "future_confirmation_phrase_executable": False,
        "no_real_telegram_send_passed": all(
            result["real_telegram_send_called"] is False and result["real_telegram_message_sent"] is False
            for result in results
        ),
        "no_secret_leak_passed": first_readiness.get("secrets_shown") is False,
        "no_mutation_passed": all(result["real_runtime_mutated"] is False for result in results),
        "recommended_next_operator_move": (
            "prepare_human_reviewed_real_telegram_synthetic_alert_send_apply_gate"
            if passed
            else "repair_r320_synthetic_send_drill_preview_blockers"
        ),
        "recommended_r321_path": RECOMMENDED_R321_APPLY_GATE if passed else RECOMMENDED_R321_REPAIR,
        "synthetic_scenario": True,
        "synthetic_inputs_used": True,
        "real_runtime_mutated": False,
        "safety": safety,
        **safety,
    }
    safe_payload = _sanitize(payload)
    if should_write:
        append_record(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def run_synthetic_real_telegram_scenario(
    *,
    scenario_name: str,
    log_dir: str | Path,
    max_age_seconds: int,
    rate_limit_window_seconds: int,
    now: datetime,
    env: Mapping[str, str] | None,
    env_file_path: str | Path | None,
) -> dict[str, Any]:
    r317_name = _r317_scenario_name(scenario_name)
    health = build_synthetic_health_panel(
        scenario_name=r317_name,
        now=now,
        max_age_seconds=max_age_seconds,
    )
    preview = build_multi_lane_observation_alerting_preview(
        log_dir=log_dir,
        max_age_seconds=max_age_seconds,
        write=False,
        now=now,
        rate_limit_window_seconds=rate_limit_window_seconds,
        health_panel=health,
    )
    preview["dedup_key"] = f"r320:{scenario_name}:{preview.get('alert_severity')}"
    real_preview = build_real_telegram_observation_alert_send_preview(
        log_dir=log_dir,
        env=env,
        max_age_seconds=max_age_seconds,
        rate_limit_window_seconds=rate_limit_window_seconds,
        no_write=True,
        write=False,
        now=now,
        alert_preview=deepcopy(dict(preview)),
        env_file_path=env_file_path,
    )
    expected_alert_required = scenario_name != SCENARIO_HEALTHY
    observed_alert_required = bool(real_preview.get("alert_required"))
    observed_severity = str(real_preview.get("alert_severity") or "")
    readiness = _mapping(real_preview.get("telegram_config_readiness"))
    credentials_ready = bool(real_preview.get("real_send_available_for_future"))
    blockers = _scenario_blockers(
        scenario_name=scenario_name,
        expected_alert_required=expected_alert_required,
        observed_alert_required=observed_alert_required,
        observed_severity=observed_severity,
        credentials_ready=credentials_ready,
        real_preview=real_preview,
    )
    safety = dict(SAFETY)
    return {
        "scenario_name": scenario_name,
        "synthetic_scenario": True,
        "synthetic_inputs_used": True,
        "real_runtime_mutated": False,
        "expected_alert_required": expected_alert_required,
        "observed_alert_required": observed_alert_required,
        "observed_alert_severity": observed_severity,
        "observed_alert_reasons": list(real_preview.get("alert_reasons") or []),
        "real_credentials_ready": credentials_ready,
        "real_send_available_for_future": credentials_ready,
        "future_real_send_eligible_after_exact_phrase": bool(expected_alert_required and credentials_ready),
        "future_confirmation_phrase_required": FUTURE_CONFIRMATION_PHRASE,
        "future_confirmation_phrase_active": False,
        "future_confirmation_phrase_executable": False,
        "would_send_real_telegram_now": False,
        "telegram_send_called": False,
        "telegram_message_sent": False,
        "real_telegram_send_called": False,
        "real_telegram_message_sent": False,
        "pass": not blockers,
        "passed": not blockers,
        "result_status": "PASS" if not blockers else "FAIL",
        "blockers": blockers,
        "telegram_config_readiness": dict(readiness),
        "source_alert_preview": preview,
        "source_real_telegram_preview": real_preview,
        "safety": safety,
        **safety,
    }


def load_real_telegram_observation_alert_synthetic_send_drill_preview_records(
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


def format_synthetic_send_drill_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), indent=2, sort_keys=True)


def format_synthetic_send_drill_text(payload: Mapping[str, Any]) -> str:
    readiness = _mapping(payload.get("telegram_config_readiness"))
    lines = [
        "R320 REAL TELEGRAM OBSERVATION ALERT SYNTHETIC SEND DRILL PREVIEW",
        "",
        "TELEGRAM CREDENTIAL READINESS",
        f"telegram_token_present: {readiness.get('telegram_token_present')}",
        f"telegram_chat_id_present: {readiness.get('telegram_chat_id_present')}",
        f"telegram_config_source_kind: {readiness.get('telegram_config_source_kind')}",
        f"telegram_config_source_path_present: {readiness.get('telegram_config_source_path_present')}",
        f"telegram_token_preview: {readiness.get('telegram_token_preview')}",
        f"telegram_chat_id_preview: {readiness.get('telegram_chat_id_preview')}",
        f"credentials_ready: {payload.get('credentials_ready')}",
        f"real_send_available_for_future: {payload.get('real_send_available_for_future')}",
        "",
        "DRILL STATUS",
        f"drill_status: {payload.get('drill_status')}",
        f"drill_blockers: {_join(payload.get('drill_blockers'))}",
        "",
        "SCENARIOS RUN",
        f"scenarios_run: {_join(payload.get('scenarios_run'))}",
        "",
        "HEALTHY NO-HEARTBEAT RESULT",
        _format_scenario_line(payload, SCENARIO_HEALTHY),
        "",
        "SYNTHETIC STALE OBSERVATION RESULT",
        _format_scenario_line(payload, SCENARIO_SYNTHETIC_STALE_OBSERVATION),
        "",
        "SYNTHETIC FINAL SAFETY VIOLATION RESULT",
        _format_scenario_line(payload, SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION),
        "",
        "FUTURE CONFIRMATION PHRASE STATUS",
        f"future_confirmation_phrase_required: {payload.get('future_confirmation_phrase_required')}",
        f"future_confirmation_phrase_active: {payload.get('future_confirmation_phrase_active')}",
        f"future_confirmation_phrase_executable: {payload.get('future_confirmation_phrase_executable')}",
        f"future_confirmation_inactive_passed: {payload.get('future_confirmation_inactive_passed')}",
        "",
        "REAL SEND PREVIEW FLAGS",
        f"real_send_preview_only: {payload.get('real_send_preview_only')}",
        f"would_send_real_telegram_now: {payload.get('would_send_real_telegram_now')}",
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
            "",
            "RECOMMENDED NEXT PHASE",
            str(payload.get("recommended_r321_path")),
        ]
    )
    return "\n".join(lines)


def _scenario_blockers(
    *,
    scenario_name: str,
    expected_alert_required: bool,
    observed_alert_required: bool,
    observed_severity: str,
    credentials_ready: bool,
    real_preview: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if observed_alert_required is not expected_alert_required:
        blockers.append("alert_required_mismatch")
    if scenario_name == SCENARIO_HEALTHY:
        if observed_severity != INFO_PREVIEW_NO_SEND:
            blockers.append("healthy_severity_not_info")
        if real_preview.get("healthy_state_send_blocked") is not True:
            blockers.append("healthy_no_heartbeat_policy_not_blocking")
    elif scenario_name == SCENARIO_SYNTHETIC_STALE_OBSERVATION and observed_severity not in {
        WARNING_PREVIEW_NO_SEND,
        CRITICAL_PREVIEW_NO_SEND,
    }:
        blockers.append("stale_severity_not_actionable")
    elif scenario_name == SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION and observed_severity != CRITICAL_PREVIEW_NO_SEND:
        blockers.append("final_safety_severity_not_critical")
    if not credentials_ready:
        blockers.append("real_credentials_not_ready")
    if real_preview.get("future_confirmation_phrase_required") != FUTURE_CONFIRMATION_PHRASE:
        blockers.append("future_confirmation_phrase_missing")
    if real_preview.get("future_confirmation_phrase_active") is not False:
        blockers.append("future_confirmation_phrase_active")
    if real_preview.get("future_confirmation_phrase_executable") is not False:
        blockers.append("future_confirmation_phrase_executable")
    false_fields = (
        "would_send_real_telegram_now",
        "telegram_send_called",
        "telegram_message_sent",
        "real_telegram_send_called",
        "real_telegram_message_sent",
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
    for field in false_fields:
        if real_preview.get(field) is not False:
            blockers.append(f"{field}_unexpected")
    return _dedupe(blockers)


def _drill_blockers(
    *,
    results: Sequence[Mapping[str, Any]],
    scenario_names: Sequence[str],
    credentials_ready: bool,
) -> list[str]:
    blockers: list[str] = []
    missing = set(scenario_names) - {str(result.get("scenario_name")) for result in results}
    if missing:
        blockers.append("missing_scenario_results")
    if not credentials_ready:
        blockers.append("real_credentials_not_ready")
    for result in results:
        if result.get("pass") is not True:
            blockers.append(f"{result.get('scenario_name')}_failed")
    return _dedupe(blockers)


def _r317_scenario_name(scenario_name: str) -> str:
    if scenario_name == SCENARIO_HEALTHY:
        return R317_SCENARIO_HEALTHY
    if scenario_name == SCENARIO_SYNTHETIC_STALE_OBSERVATION:
        return R317_SCENARIO_STALE_OBSERVATION
    if scenario_name == SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION:
        return R317_SCENARIO_FINAL_SAFETY_VIOLATION
    raise ValueError(f"unsupported synthetic scenario: {scenario_name}")


def _first_readiness(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    for result in results:
        readiness = result.get("telegram_config_readiness")
        if isinstance(readiness, Mapping):
            return dict(readiness)
    return {}


def _scenario_passed(results: Sequence[Mapping[str, Any]], scenario_name: str) -> bool:
    for result in results:
        if result.get("scenario_name") == scenario_name:
            return result.get("pass") is True
    return False


def _format_scenario_line(payload: Mapping[str, Any], scenario_name: str) -> str:
    for result in payload.get("scenario_results") or []:
        if isinstance(result, Mapping) and result.get("scenario_name") == scenario_name:
            return (
                f"{result.get('result_status')} | alert_required={result.get('observed_alert_required')} | "
                f"severity={result.get('observed_alert_severity')} | "
                f"real_credentials_ready={result.get('real_credentials_ready')} | "
                f"future_real_send_eligible_after_exact_phrase="
                f"{result.get('future_real_send_eligible_after_exact_phrase')} | "
                f"would_send_real_telegram_now={result.get('would_send_real_telegram_now')} | "
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
        prog="python -m src.app.hammer_radar.operator.real_telegram_observation_alert_synthetic_send_drill_preview"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--scenario", choices=(*SCENARIOS, SCENARIO_ALL), default=SCENARIO_ALL)
    parser.add_argument("--max-age-seconds", type=int, default=180)
    parser.add_argument("--rate-limit-window-seconds", type=int, default=DEFAULT_RATE_LIMIT_WINDOW_SECONDS)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    payload = build_real_telegram_observation_alert_synthetic_send_drill_preview(
        log_dir=args.log_dir,
        scenario=args.scenario,
        max_age_seconds=args.max_age_seconds,
        rate_limit_window_seconds=args.rate_limit_window_seconds,
        no_write=args.no_write,
    )
    if args.json and not args.text:
        print(format_synthetic_send_drill_json(payload))
    else:
        print(format_synthetic_send_drill_text(payload))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint.
    raise SystemExit(main())
