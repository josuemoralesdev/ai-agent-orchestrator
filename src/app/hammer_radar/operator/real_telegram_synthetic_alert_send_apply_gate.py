"""R321 human-reviewed real Telegram synthetic alert send apply gate.

This gate prepares the operator command shape for a future real Telegram
synthetic alert test while keeping Codex validation unable to send real
Telegram. Only mock sends can be recorded here.
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

EVENT_TYPE = "R321_HUMAN_REVIEWED_REAL_TELEGRAM_SYNTHETIC_ALERT_SEND_APPLY_GATE"
CREATED_BY_PHASE = "R321_HUMAN_REVIEWED_REAL_TELEGRAM_SYNTHETIC_ALERT_SEND_APPLY_GATE"
LEDGER_FILENAME = "real_telegram_synthetic_alert_send_apply_gate.ndjson"

SCENARIO_HEALTHY = "healthy"
SCENARIO_SYNTHETIC_STALE_OBSERVATION = "synthetic_stale_observation"
SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION = "synthetic_final_safety_violation"
SCENARIOS = (
    SCENARIO_HEALTHY,
    SCENARIO_SYNTHETIC_STALE_OBSERVATION,
    SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION,
)

TELEGRAM_SENDER_MODE_MOCK = "mock"
TELEGRAM_SENDER_MODE_REAL_DISABLED = "real-disabled"

SEND_GATE_PREVIEW_READY = "REAL_TELEGRAM_SYNTHETIC_SEND_GATE_PREVIEW_READY"
SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED = "REAL_TELEGRAM_SYNTHETIC_SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED"
SEND_GATE_BLOCKED_NO_ALERT_REQUIRED = "REAL_TELEGRAM_SYNTHETIC_SEND_GATE_BLOCKED_NO_ALERT_REQUIRED"
SEND_GATE_BLOCKED_CREDENTIALS_REQUIRED = "REAL_TELEGRAM_SYNTHETIC_SEND_GATE_BLOCKED_CREDENTIALS_REQUIRED"
SEND_GATE_MOCK_SENT = "REAL_TELEGRAM_SYNTHETIC_SEND_GATE_MOCK_SENT"
SEND_GATE_REAL_SEND_DISABLED_IN_CODEX = "REAL_TELEGRAM_SYNTHETIC_SEND_GATE_REAL_SEND_DISABLED_IN_CODEX"

RECOMMENDED_R322_OPERATOR_PACKET = "R322 Operator-Run Real Telegram Synthetic Alert Send Activation Packet"
RECOMMENDED_R322_REPAIR = "R322 Real Telegram Synthetic Alert Send Apply Gate Repair"

SAFETY = {
    **R315_SAFETY,
    "telegram_send_called": False,
    "telegram_message_sent": False,
    "real_telegram_send_called": False,
    "real_telegram_message_sent": False,
    "would_send_real_telegram_now": False,
    "real_send_preview_only": True,
}


def build_real_telegram_synthetic_alert_send_apply_gate(
    *,
    log_dir: str | Path | None = None,
    apply: bool = False,
    confirmation: str | None = None,
    scenario: str = SCENARIO_SYNTHETIC_STALE_OBSERVATION,
    telegram_sender_mode: str = TELEGRAM_SENDER_MODE_MOCK,
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
    if scenario not in SCENARIOS:
        raise ValueError(f"unsupported synthetic scenario: {scenario}")
    mode = (
        TELEGRAM_SENDER_MODE_REAL_DISABLED
        if telegram_sender_mode == TELEGRAM_SENDER_MODE_REAL_DISABLED
        else TELEGRAM_SENDER_MODE_MOCK
    )

    preview = _build_synthetic_alert_preview(
        scenario=scenario,
        log_dir=resolved_log_dir,
        max_age_seconds=max_age_seconds,
        rate_limit_window_seconds=rate_limit_window_seconds,
        now=generated_at,
    )
    real_preview = build_real_telegram_observation_alert_send_preview(
        log_dir=resolved_log_dir,
        env=env,
        max_age_seconds=max_age_seconds,
        rate_limit_window_seconds=rate_limit_window_seconds,
        no_write=True,
        write=False,
        now=generated_at,
        alert_preview=deepcopy(preview),
        env_file_path=env_file_path,
    )

    alert_required = bool(real_preview.get("alert_required"))
    severity = str(real_preview.get("alert_severity") or INFO_PREVIEW_NO_SEND)
    credentials_ready = bool(real_preview.get("real_send_available_for_future"))
    confirmation_matched = str(confirmation or "") == FUTURE_CONFIRMATION_PHRASE
    blockers = _send_blockers(
        apply_requested=apply,
        confirmation_phrase_matched=confirmation_matched,
        alert_required=alert_required,
        severity=severity,
        credentials_ready=credentials_ready,
        telegram_sender_mode=mode,
    )
    status = _send_gate_status(
        apply_requested=apply,
        confirmation_phrase_matched=confirmation_matched,
        alert_required=alert_required,
        credentials_ready=credentials_ready,
        telegram_sender_mode=mode,
    )
    mock_sent = status == SEND_GATE_MOCK_SENT
    safety = dict(SAFETY)
    safety.update(
        {
            "telegram_send_called": mock_sent,
            "telegram_message_sent": mock_sent,
            "real_telegram_send_called": False,
            "real_telegram_message_sent": False,
            "would_send_real_telegram_now": False,
            "real_send_preview_only": True,
        }
    )
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "send_gate_id": f"r321_real_telegram_synthetic_alert_send_apply_gate_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ledger_path": str(records_path(resolved_log_dir)),
        "scenario": scenario,
        "synthetic_scenario": scenario != SCENARIO_HEALTHY,
        "synthetic_inputs_used": True,
        "real_runtime_mutated": False,
        "apply_requested": bool(apply),
        "confirmation_phrase_required": FUTURE_CONFIRMATION_PHRASE,
        "confirmation_phrase_matched": confirmation_matched,
        "telegram_sender_mode": mode,
        "telegram_config_readiness": dict(_mapping(real_preview.get("telegram_config_readiness"))),
        "credentials_ready": credentials_ready,
        "alert_required": alert_required,
        "alert_severity": severity,
        "alert_reasons": list(real_preview.get("alert_reasons") or []),
        "send_gate_status": status,
        "send_blockers": blockers,
        "real_send_preview_only": True,
        "would_send_real_telegram_now": False,
        "telegram_send_called": mock_sent,
        "telegram_message_sent": mock_sent,
        "real_telegram_send_called": False,
        "real_telegram_message_sent": False,
        "telegram_message_preview": str(real_preview.get("telegram_preview_message") or ""),
        "operator_console_preview": str(real_preview.get("operator_console_preview_message") or ""),
        "no_secret_leak_passed": real_preview.get("secrets_shown") is False,
        "no_mutation_passed": _no_mutation_passed(real_preview),
        "recommended_next_operator_move": _recommended_next_operator_move(status),
        "recommended_r322_path": _recommended_r322_path(status),
        "source_alert_preview": preview,
        "source_real_telegram_preview": real_preview,
        "safety": safety,
        **safety,
    }
    safe_payload = _sanitize(payload)
    if should_write:
        append_record(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def load_real_telegram_synthetic_alert_send_apply_gate_records(
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


def format_real_telegram_synthetic_alert_send_apply_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), indent=2, sort_keys=True)


def format_real_telegram_synthetic_alert_send_apply_gate_text(payload: Mapping[str, Any]) -> str:
    readiness = _mapping(payload.get("telegram_config_readiness"))
    lines = [
        "R321 HUMAN-REVIEWED REAL TELEGRAM SYNTHETIC ALERT SEND APPLY GATE",
        "",
        "SCENARIO",
        f"scenario: {payload.get('scenario')}",
        f"synthetic_scenario: {payload.get('synthetic_scenario')}",
        f"synthetic_inputs_used: {payload.get('synthetic_inputs_used')}",
        "",
        "APPLY / CONFIRMATION STATUS",
        f"apply_requested: {payload.get('apply_requested')}",
        f"confirmation_phrase_required: {payload.get('confirmation_phrase_required')}",
        f"confirmation_phrase_matched: {payload.get('confirmation_phrase_matched')}",
        "",
        "TELEGRAM CREDENTIAL READINESS",
        f"telegram_token_present: {readiness.get('telegram_token_present')}",
        f"telegram_chat_id_present: {readiness.get('telegram_chat_id_present')}",
        f"telegram_config_source_kind: {readiness.get('telegram_config_source_kind')}",
        f"telegram_config_source_path_present: {readiness.get('telegram_config_source_path_present')}",
        f"telegram_token_preview: {readiness.get('telegram_token_preview')}",
        f"telegram_chat_id_preview: {readiness.get('telegram_chat_id_preview')}",
        f"credentials_ready: {payload.get('credentials_ready')}",
        "",
        "ALERT SUMMARY",
        f"alert_required: {payload.get('alert_required')}",
        f"alert_severity: {payload.get('alert_severity')}",
        f"alert_reasons: {_join(payload.get('alert_reasons'))}",
        "",
        "SEND GATE STATUS",
        f"send_gate_status: {payload.get('send_gate_status')}",
        f"send_blockers: {_join(payload.get('send_blockers'))}",
        f"real_send_preview_only: {payload.get('real_send_preview_only')}",
        f"would_send_real_telegram_now: {payload.get('would_send_real_telegram_now')}",
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
            "",
            "RECOMMENDED NEXT PHASE",
            str(payload.get("recommended_r322_path")),
        ]
    )
    return "\n".join(lines)


def _build_synthetic_alert_preview(
    *,
    scenario: str,
    log_dir: str | Path,
    max_age_seconds: int,
    rate_limit_window_seconds: int,
    now: datetime,
) -> dict[str, Any]:
    health = build_synthetic_health_panel(
        scenario_name=_r317_scenario_name(scenario),
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
    preview["dedup_key"] = f"r321:{scenario}:{preview.get('alert_severity')}"
    return _sanitize(preview)


def _send_blockers(
    *,
    apply_requested: bool,
    confirmation_phrase_matched: bool,
    alert_required: bool,
    severity: str,
    credentials_ready: bool,
    telegram_sender_mode: str,
) -> list[str]:
    blockers: list[str] = []
    if not apply_requested:
        return blockers
    if not confirmation_phrase_matched:
        blockers.append("confirmation_phrase_required")
    if not alert_required:
        blockers.append("alert_required_false")
    if severity == INFO_PREVIEW_NO_SEND:
        blockers.append("info_preview_no_action_never_sends")
    if severity not in {WARNING_PREVIEW_NO_SEND, CRITICAL_PREVIEW_NO_SEND}:
        blockers.append("alert_severity_not_sendable")
    if not credentials_ready:
        blockers.append("telegram_credentials_required")
    if telegram_sender_mode == TELEGRAM_SENDER_MODE_REAL_DISABLED:
        blockers.append("real_send_disabled_in_codex")
    return _dedupe(blockers)


def _send_gate_status(
    *,
    apply_requested: bool,
    confirmation_phrase_matched: bool,
    alert_required: bool,
    credentials_ready: bool,
    telegram_sender_mode: str,
) -> str:
    if not apply_requested:
        return SEND_GATE_PREVIEW_READY
    if not alert_required:
        return SEND_GATE_BLOCKED_NO_ALERT_REQUIRED
    if not confirmation_phrase_matched:
        return SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED
    if not credentials_ready:
        return SEND_GATE_BLOCKED_CREDENTIALS_REQUIRED
    if telegram_sender_mode == TELEGRAM_SENDER_MODE_REAL_DISABLED:
        return SEND_GATE_REAL_SEND_DISABLED_IN_CODEX
    return SEND_GATE_MOCK_SENT


def _recommended_next_operator_move(status: str) -> str:
    if status == SEND_GATE_PREVIEW_READY:
        return "review_exact_phrase_and_operator_apply_gate"
    if status == SEND_GATE_MOCK_SENT:
        return "review_mock_send_record_before_any_real_operator_packet"
    if status == SEND_GATE_REAL_SEND_DISABLED_IN_CODEX:
        return "keep_real_send_disabled_in_codex_prepare_operator_activation_packet"
    return "repair_or_review_apply_gate_blockers_before_any_send"


def _recommended_r322_path(status: str) -> str:
    if status in {SEND_GATE_PREVIEW_READY, SEND_GATE_MOCK_SENT, SEND_GATE_REAL_SEND_DISABLED_IN_CODEX}:
        return RECOMMENDED_R322_OPERATOR_PACKET
    return RECOMMENDED_R322_REPAIR


def _r317_scenario_name(scenario: str) -> str:
    if scenario == SCENARIO_HEALTHY:
        return R317_SCENARIO_HEALTHY
    if scenario == SCENARIO_SYNTHETIC_STALE_OBSERVATION:
        return R317_SCENARIO_STALE_OBSERVATION
    if scenario == SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION:
        return R317_SCENARIO_FINAL_SAFETY_VIOLATION
    raise ValueError(f"unsupported synthetic scenario: {scenario}")


def _no_mutation_passed(real_preview: Mapping[str, Any]) -> bool:
    false_fields = (
        "config_written",
        "risk_contract_config_mutated",
        "autonomous_arming_state_changed",
        "global_live_flags_changed",
        "env_written",
        "env_mutated",
        "systemd_unit_mutated",
        "scheduler_started",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "leverage_change_called",
        "margin_change_called",
        "submit_allowed",
        "final_command_available",
    )
    return all(real_preview.get(field) is False for field in false_fields)


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
        prog="python -m src.app.hammer_radar.operator.real_telegram_synthetic_alert_send_apply_gate"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirmation", default=None)
    parser.add_argument("--scenario", choices=SCENARIOS, default=SCENARIO_SYNTHETIC_STALE_OBSERVATION)
    parser.add_argument(
        "--telegram-sender-mode",
        choices=(TELEGRAM_SENDER_MODE_MOCK, TELEGRAM_SENDER_MODE_REAL_DISABLED),
        default=TELEGRAM_SENDER_MODE_MOCK,
    )
    parser.add_argument("--max-age-seconds", type=int, default=180)
    parser.add_argument("--rate-limit-window-seconds", type=int, default=DEFAULT_RATE_LIMIT_WINDOW_SECONDS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    payload = build_real_telegram_synthetic_alert_send_apply_gate(
        log_dir=args.log_dir,
        apply=args.apply,
        confirmation=args.confirmation,
        scenario=args.scenario,
        telegram_sender_mode=args.telegram_sender_mode,
        max_age_seconds=args.max_age_seconds,
        rate_limit_window_seconds=args.rate_limit_window_seconds,
        no_write=args.no_write,
    )
    if args.json and not args.text:
        print(format_real_telegram_synthetic_alert_send_apply_gate_json(payload))
    else:
        print(format_real_telegram_synthetic_alert_send_apply_gate_text(payload))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint.
    raise SystemExit(main())
