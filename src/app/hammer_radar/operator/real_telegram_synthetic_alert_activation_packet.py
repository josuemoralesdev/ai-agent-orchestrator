"""R322 operator-run real Telegram synthetic alert activation packet.

This packet reuses the R321 apply gate proof paths and prints an operator
activation packet. It never adds or invokes a real Telegram sender mode.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.multi_lane_observation_alerting_preview import (
    DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
)
from src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview import (
    FUTURE_CONFIRMATION_PHRASE,
)
from src.app.hammer_radar.operator.real_telegram_synthetic_alert_send_apply_gate import (
    SAFETY as R321_SAFETY,
    SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION,
    SCENARIO_SYNTHETIC_STALE_OBSERVATION,
    SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED,
    SEND_GATE_MOCK_SENT,
    SEND_GATE_PREVIEW_READY,
    SEND_GATE_REAL_SEND_DISABLED_IN_CODEX,
    build_real_telegram_synthetic_alert_send_apply_gate,
)

EVENT_TYPE = "R322_OPERATOR_RUN_REAL_TELEGRAM_SYNTHETIC_ALERT_SEND_ACTIVATION_PACKET"
CREATED_BY_PHASE = "R322_OPERATOR_RUN_REAL_TELEGRAM_SYNTHETIC_ALERT_SEND_ACTIVATION_PACKET"
LEDGER_FILENAME = "real_telegram_synthetic_alert_activation_packet.ndjson"

ACTIVATION_PACKET_READY = "REAL_TELEGRAM_SYNTHETIC_ALERT_ACTIVATION_PACKET_READY"
ACTIVATION_PACKET_BLOCKED = "REAL_TELEGRAM_SYNTHETIC_ALERT_ACTIVATION_PACKET_BLOCKED"

REAL_SEND_MANUAL_ONLY_STATUS = "not_available_in_current_code_r321_has_no_real_sender_mode"
REAL_SEND_MANUAL_ONLY_COMMAND = (
    "# MANUAL ONLY - NOT EXECUTABLE IN R322: R321 exposes only --telegram-sender-mode mock|real-disabled; "
    "--telegram-sender-mode real is intentionally unavailable."
)
REAL_SEND_MANUAL_ONLY_WARNING = (
    "MANUAL ONLY. NOT EXECUTED BY CODEX. R322 does not add a real sender mode, does not call Telegram, "
    "and does not make this command executable."
)
RECOMMENDED_R323_PATH = "R323 Strategy Lab Expansion Re-entry and Candidate Surface Map"

SCENARIOS = (SCENARIO_SYNTHETIC_STALE_OBSERVATION, SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION)

SAFE_PREVIEW_COMMAND = (
    "PYTHONPATH=. .venv/bin/python -m "
    "src.app.hammer_radar.operator.real_telegram_synthetic_alert_send_apply_gate "
    "--log-dir logs/hammer_radar_forward --json"
)
MOCK_APPLY_COMMAND_TEMPLATE = (
    "PYTHONPATH=. .venv/bin/python -m "
    "src.app.hammer_radar.operator.real_telegram_synthetic_alert_send_apply_gate "
    '--log-dir logs/hammer_radar_forward --apply --confirmation "{confirmation}" '
    "--telegram-sender-mode mock --scenario {scenario} --json"
)
REAL_DISABLED_COMMAND_TEMPLATE = (
    "PYTHONPATH=. .venv/bin/python -m "
    "src.app.hammer_radar.operator.real_telegram_synthetic_alert_send_apply_gate "
    '--log-dir logs/hammer_radar_forward --apply --confirmation "{confirmation}" '
    "--telegram-sender-mode real-disabled --scenario {scenario} --json"
)

SAFETY = {
    **R321_SAFETY,
    "telegram_send_called": False,
    "telegram_message_sent": False,
    "real_telegram_send_called": False,
    "real_telegram_message_sent": False,
    "would_send_real_telegram_now": False,
    "real_send_preview_only": True,
}


def build_real_telegram_synthetic_alert_activation_packet(
    *,
    log_dir: str | Path | None = None,
    scenario: str = SCENARIO_SYNTHETIC_STALE_OBSERVATION,
    max_age_seconds: int = 180,
    rate_limit_window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
    no_write: bool = False,
    write: bool | None = None,
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
    env_file_path: str | Path | None = None,
) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise ValueError(f"unsupported synthetic scenario: {scenario}")

    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    should_write = (not no_write) if write is None else bool(write)

    preview = build_real_telegram_synthetic_alert_send_apply_gate(
        log_dir=resolved_log_dir,
        scenario=scenario,
        max_age_seconds=max_age_seconds,
        rate_limit_window_seconds=rate_limit_window_seconds,
        no_write=True,
        write=False,
        now=generated_at,
        env=env,
        env_file_path=env_file_path,
    )
    wrong_phrase = build_real_telegram_synthetic_alert_send_apply_gate(
        log_dir=resolved_log_dir,
        apply=True,
        confirmation="WRONG PHRASE",
        scenario=scenario,
        telegram_sender_mode="mock",
        max_age_seconds=max_age_seconds,
        rate_limit_window_seconds=rate_limit_window_seconds,
        no_write=True,
        write=False,
        now=generated_at,
        env=env,
        env_file_path=env_file_path,
    )
    mock_apply = build_real_telegram_synthetic_alert_send_apply_gate(
        log_dir=resolved_log_dir,
        apply=True,
        confirmation=FUTURE_CONFIRMATION_PHRASE,
        scenario=scenario,
        telegram_sender_mode="mock",
        max_age_seconds=max_age_seconds,
        rate_limit_window_seconds=rate_limit_window_seconds,
        no_write=True,
        write=False,
        now=generated_at,
        env=env,
        env_file_path=env_file_path,
    )
    real_disabled = build_real_telegram_synthetic_alert_send_apply_gate(
        log_dir=resolved_log_dir,
        apply=True,
        confirmation=FUTURE_CONFIRMATION_PHRASE,
        scenario=scenario,
        telegram_sender_mode="real-disabled",
        max_age_seconds=max_age_seconds,
        rate_limit_window_seconds=rate_limit_window_seconds,
        no_write=True,
        write=False,
        now=generated_at,
        env=env,
        env_file_path=env_file_path,
    )

    telegram_config_readiness = dict(_mapping(preview.get("telegram_config_readiness")))
    credentials_ready = bool(preview.get("credentials_ready"))
    no_secret_leak_passed = all(
        payload.get("no_secret_leak_passed") is True and payload.get("secrets_shown") is False
        for payload in (preview, wrong_phrase, mock_apply, real_disabled)
    )
    no_mutation_passed = all(
        payload.get("no_mutation_passed") is True and _all_safety_flags_expected(payload)
        for payload in (preview, wrong_phrase, mock_apply, real_disabled)
    )
    blockers = _activation_packet_blockers(
        credentials_ready=credentials_ready,
        preview=preview,
        wrong_phrase=wrong_phrase,
        mock_apply=mock_apply,
        real_disabled=real_disabled,
        no_secret_leak_passed=no_secret_leak_passed,
        no_mutation_passed=no_mutation_passed,
    )
    packet_ready = not blockers
    safety = dict(SAFETY)
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "activation_packet_id": f"r322_real_telegram_synthetic_alert_activation_packet_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ledger_path": str(records_path(resolved_log_dir)),
        "activation_packet_status": ACTIVATION_PACKET_READY if packet_ready else ACTIVATION_PACKET_BLOCKED,
        "activation_packet_blockers": blockers,
        "scenario": scenario,
        "synthetic_scenario": True,
        "synthetic_inputs_used": True,
        "real_runtime_mutated": False,
        "confirmation_phrase_required": FUTURE_CONFIRMATION_PHRASE,
        "telegram_config_readiness": telegram_config_readiness,
        "credentials_ready": credentials_ready,
        "r321_preview_status": preview.get("send_gate_status"),
        "r321_wrong_phrase_block_status": wrong_phrase.get("send_gate_status"),
        "r321_mock_apply_status": mock_apply.get("send_gate_status"),
        "r321_real_disabled_status": real_disabled.get("send_gate_status"),
        "safe_preview_command": SAFE_PREVIEW_COMMAND,
        "mock_apply_command": MOCK_APPLY_COMMAND_TEMPLATE.format(
            confirmation=FUTURE_CONFIRMATION_PHRASE,
            scenario=scenario,
        ),
        "real_disabled_command": REAL_DISABLED_COMMAND_TEMPLATE.format(
            confirmation=FUTURE_CONFIRMATION_PHRASE,
            scenario=scenario,
        ),
        "real_send_command_manual_only": REAL_SEND_MANUAL_ONLY_COMMAND,
        "real_send_command_manual_only_status": REAL_SEND_MANUAL_ONLY_STATUS,
        "real_send_command_manual_only_warning": REAL_SEND_MANUAL_ONLY_WARNING,
        "operator_preflight_checklist": operator_preflight_checklist(),
        "operator_abort_conditions": operator_abort_conditions(),
        "expected_success_result_if_operator_runs_real_send": expected_success_result_if_operator_runs_real_send(),
        "codex_validation_real_send_forbidden": True,
        "codex_validation_sent_real_telegram": False,
        "telegram_send_called": False,
        "telegram_message_sent": False,
        "real_telegram_send_called": False,
        "real_telegram_message_sent": False,
        "would_send_real_telegram_now": False,
        "real_send_preview_only": True,
        "no_secret_leak_passed": no_secret_leak_passed,
        "no_mutation_passed": no_mutation_passed,
        "recommended_next_operator_move": (
            "operator_may_review_activation_packet_then_return_to_strategy_lab"
            if packet_ready
            else "repair_activation_packet_blockers_before_any_operator_send"
        ),
        "recommended_r323_path": RECOMMENDED_R323_PATH,
        "source_r321_preview": preview,
        "source_r321_wrong_phrase_block": wrong_phrase,
        "source_r321_mock_apply": mock_apply,
        "source_r321_real_disabled": real_disabled,
        "safety": safety,
        **safety,
    }
    safe_payload = _sanitize(payload)
    if should_write:
        append_record(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def operator_preflight_checklist() -> list[str]:
    return [
        "R321 committed",
        "Telegram credentials ready and masked",
        "safe preview command passes",
        "wrong phrase blocks",
        "mock apply records mock send only",
        "real-disabled path blocks real send",
        "no secret leak scan clean",
        "no env mutation",
        "no config/arming mutation",
        "no systemd mutation",
        "live safety still locked",
        "no current real trade execution triggered",
        "operator understands this is a Telegram synthetic alert only, not a trade",
    ]


def operator_abort_conditions() -> list[str]:
    return [
        "credentials missing",
        "any raw secret appears",
        "real_order_forbidden=false",
        "submit_allowed=true",
        "final_command_available=true",
        "config/arming diff present",
        ".env changed",
        "systemd service changed",
        "unexpected Telegram send already occurred",
        "alert scenario is not synthetic",
        "command would touch Binance or trading endpoints",
    ]


def expected_success_result_if_operator_runs_real_send() -> dict[str, Any]:
    return {
        "telegram_message_sent": True,
        "real_telegram_message_sent": True,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "submit_allowed": False,
        "final_command_available": False,
        "binance_order_endpoint_called": False,
        "binance_test_order_endpoint_called": False,
        "note": "Expected only for a future operator-reviewed real Telegram sender patch, not R322.",
    }


def load_real_telegram_synthetic_alert_activation_packet_records(
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


def format_real_telegram_synthetic_alert_activation_packet_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), indent=2, sort_keys=True)


def format_real_telegram_synthetic_alert_activation_packet_text(payload: Mapping[str, Any]) -> str:
    readiness = _mapping(payload.get("telegram_config_readiness"))
    lines = [
        "R322 OPERATOR-RUN REAL TELEGRAM SYNTHETIC ALERT SEND ACTIVATION PACKET",
        "",
        "ACTIVATION PACKET STATUS",
        f"activation_packet_status: {payload.get('activation_packet_status')}",
        f"activation_packet_blockers: {_join(payload.get('activation_packet_blockers'))}",
        f"scenario: {payload.get('scenario')}",
        f"synthetic_scenario: {payload.get('synthetic_scenario')}",
        f"synthetic_inputs_used: {payload.get('synthetic_inputs_used')}",
        "",
        "TELEGRAM READINESS",
        f"telegram_token_present: {readiness.get('telegram_token_present')}",
        f"telegram_chat_id_present: {readiness.get('telegram_chat_id_present')}",
        f"telegram_config_source_kind: {readiness.get('telegram_config_source_kind')}",
        f"telegram_config_source_path_present: {readiness.get('telegram_config_source_path_present')}",
        f"telegram_token_preview: {readiness.get('telegram_token_preview')}",
        f"telegram_chat_id_preview: {readiness.get('telegram_chat_id_preview')}",
        f"credentials_ready: {payload.get('credentials_ready')}",
        "",
        "R321 GATE PROOF SUMMARY",
        f"r321_preview_status: {payload.get('r321_preview_status')}",
        f"r321_wrong_phrase_block_status: {payload.get('r321_wrong_phrase_block_status')}",
        f"r321_mock_apply_status: {payload.get('r321_mock_apply_status')}",
        f"r321_real_disabled_status: {payload.get('r321_real_disabled_status')}",
        "",
        "SAFE PREVIEW COMMAND",
        str(payload.get("safe_preview_command") or ""),
        "",
        "MOCK APPLY COMMAND",
        str(payload.get("mock_apply_command") or ""),
        "",
        "REAL-DISABLED COMMAND",
        str(payload.get("real_disabled_command") or ""),
        "",
        "MANUAL-ONLY REAL-SEND STATUS",
        f"real_send_command_manual_only_status: {payload.get('real_send_command_manual_only_status')}",
        f"real_send_command_manual_only: {payload.get('real_send_command_manual_only')}",
        f"real_send_command_manual_only_warning: {payload.get('real_send_command_manual_only_warning')}",
        "",
        "OPERATOR PREFLIGHT CHECKLIST",
    ]
    lines.extend(f"- {item}" for item in payload.get("operator_preflight_checklist") or [])
    lines.extend(["", "OPERATOR ABORT CONDITIONS"])
    lines.extend(f"- {item}" for item in payload.get("operator_abort_conditions") or [])
    lines.extend(
        [
            "",
            "CODEX VALIDATION REAL-SEND FLAGS",
            f"codex_validation_real_send_forbidden: {payload.get('codex_validation_real_send_forbidden')}",
            f"codex_validation_sent_real_telegram: {payload.get('codex_validation_sent_real_telegram')}",
            f"telegram_send_called: {payload.get('telegram_send_called')}",
            f"telegram_message_sent: {payload.get('telegram_message_sent')}",
            f"real_telegram_send_called: {payload.get('real_telegram_send_called')}",
            f"real_telegram_message_sent: {payload.get('real_telegram_message_sent')}",
            f"would_send_real_telegram_now: {payload.get('would_send_real_telegram_now')}",
            f"real_send_preview_only: {payload.get('real_send_preview_only')}",
            "",
            "SAFETY FLAGS",
        ]
    )
    for key in SAFETY:
        lines.append(f"{key}: {payload.get(key)}")
    lines.extend(
        [
            "",
            "RECOMMENDED NEXT PHASE",
            str(payload.get("recommended_r323_path")),
        ]
    )
    return "\n".join(lines)


def _activation_packet_blockers(
    *,
    credentials_ready: bool,
    preview: Mapping[str, Any],
    wrong_phrase: Mapping[str, Any],
    mock_apply: Mapping[str, Any],
    real_disabled: Mapping[str, Any],
    no_secret_leak_passed: bool,
    no_mutation_passed: bool,
) -> list[str]:
    blockers: list[str] = []
    if not credentials_ready:
        blockers.append("telegram_credentials_missing")
    if preview.get("send_gate_status") != SEND_GATE_PREVIEW_READY:
        blockers.append("r321_preview_not_ready")
    if wrong_phrase.get("send_gate_status") != SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED:
        blockers.append("r321_wrong_phrase_did_not_block")
    if mock_apply.get("send_gate_status") != SEND_GATE_MOCK_SENT:
        blockers.append("r321_mock_apply_not_mock_sent")
    if real_disabled.get("send_gate_status") != SEND_GATE_REAL_SEND_DISABLED_IN_CODEX:
        blockers.append("r321_real_disabled_path_not_blocked")
    for name, payload in (
        ("preview", preview),
        ("wrong_phrase", wrong_phrase),
        ("mock_apply", mock_apply),
        ("real_disabled", real_disabled),
    ):
        if payload.get("real_telegram_send_called") is not False:
            blockers.append(f"r321_{name}_real_telegram_send_called")
        if payload.get("real_telegram_message_sent") is not False:
            blockers.append(f"r321_{name}_real_telegram_message_sent")
    if not no_secret_leak_passed:
        blockers.append("no_secret_leak_failed")
    if not no_mutation_passed:
        blockers.append("no_mutation_failed")
    return _dedupe(blockers)


def _all_safety_flags_expected(payload: Mapping[str, Any]) -> bool:
    for key, expected in SAFETY.items():
        if key in {"telegram_send_called", "telegram_message_sent"}:
            continue
        if payload.get(key) is not expected:
            return False
    return True


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
        prog="python -m src.app.hammer_radar.operator.real_telegram_synthetic_alert_activation_packet"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--scenario", choices=SCENARIOS, default=SCENARIO_SYNTHETIC_STALE_OBSERVATION)
    parser.add_argument("--max-age-seconds", type=int, default=180)
    parser.add_argument("--rate-limit-window-seconds", type=int, default=DEFAULT_RATE_LIMIT_WINDOW_SECONDS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    payload = build_real_telegram_synthetic_alert_activation_packet(
        log_dir=args.log_dir,
        scenario=args.scenario,
        max_age_seconds=args.max_age_seconds,
        rate_limit_window_seconds=args.rate_limit_window_seconds,
        no_write=args.no_write,
    )
    if args.json and not args.text:
        print(format_real_telegram_synthetic_alert_activation_packet_json(payload))
    else:
        print(format_real_telegram_synthetic_alert_activation_packet_text(payload))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint.
    raise SystemExit(main())
