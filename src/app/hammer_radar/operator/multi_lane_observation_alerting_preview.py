"""R315 multi-lane observation alerting preview.

This module previews operator/Telegram alert text from the R314 health panel.
It never sends Telegram, installs timers, mutates config/arming/env/systemd, or
creates order/final-command material.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.multi_lane_observation_health_panel import (
    HEALTH_BLOCKED,
    HEALTH_OK,
    SAFETY as R314_SAFETY,
    build_multi_lane_observation_health_panel,
)
from src.app.hammer_radar.operator.paper_refresh_scheduler import (
    PAPER_REFRESH_CRITICAL_FAILURE,
    PAPER_REFRESH_DEGRADED_NON_CRITICAL,
    TASK_ETH_PAPER_OUTCOME,
)

EVENT_TYPE = "R315_MULTI_LANE_OBSERVATION_ALERTING_PREVIEW"
CREATED_BY_PHASE = "R315_MULTI_LANE_OBSERVATION_ALERTING_PREVIEW"
LEDGER_FILENAME = "multi_lane_observation_alerting_preview.ndjson"

INFO_PREVIEW_NO_SEND = "INFO_PREVIEW_NO_SEND"
WARNING_PREVIEW_NO_SEND = "WARNING_PREVIEW_NO_SEND"
CRITICAL_PREVIEW_NO_SEND = "CRITICAL_PREVIEW_NO_SEND"

DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 900
RECOMMENDED_R316_SEND_GATE = "R316 Human-Reviewed Observation Alert Send Gate"
RECOMMENDED_R316_REPAIR = "R316 Alerting Preview Repair"

SAFETY = {
    **R314_SAFETY,
    "telegram_send_called": False,
    "telegram_message_sent": False,
}

CRITICAL_REASONS = {
    "health_status_blocked",
    "primary_contract_invalid",
    "primary_observation_status_not_ok",
    "candidate_freshness_critical",
    "final_live_safety_real_order_not_forbidden",
    "final_live_safety_submit_allowed",
    "final_live_safety_final_command_available",
    "armed_lane_changed_unexpectedly",
    "paper_refresh_critical_failure",
}


def build_multi_lane_observation_alerting_preview(
    *,
    log_dir: str | Path | None = None,
    max_age_seconds: int = 180,
    no_write: bool = False,
    write: bool | None = None,
    now: datetime | None = None,
    health_panel: Mapping[str, Any] | None = None,
    rate_limit_window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    should_write = (not no_write) if write is None else bool(write)
    source = (
        _sanitize(health_panel)
        if health_panel is not None
        else build_multi_lane_observation_health_panel(
            log_dir=resolved_log_dir,
            max_age_seconds=max_age_seconds,
            write=False,
            now=generated_at,
        )
    )
    reasons = evaluate_alert_reasons(source, max_age_seconds=max_age_seconds)
    severity = _severity(reasons)
    alert_required = severity != INFO_PREVIEW_NO_SEND
    affected_surface = _affected_surface(reasons)
    dedup_key = build_dedup_key(
        severity=severity,
        reasons=reasons,
        affected_surface=affected_surface,
    )
    rate_limit = evaluate_rate_limit_preview(
        log_dir=resolved_log_dir,
        dedup_key=dedup_key,
        now=generated_at,
        rate_limit_window_seconds=rate_limit_window_seconds,
        severity=severity,
    )
    telegram_message = build_preview_message(
        source,
        severity=severity,
        reasons=reasons,
        channel="telegram",
    )
    console_message = build_preview_message(
        source,
        severity=severity,
        reasons=reasons,
        channel="operator_console",
    )
    safety = dict(SAFETY)
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "preview_id": f"r315_multi_lane_observation_alerting_preview_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ledger_path": str(records_path(resolved_log_dir)),
        "source_event_type": source.get("event_type"),
        "source_health_status": source.get("health_status"),
        "alert_required": alert_required,
        "alert_severity": severity,
        "alert_reasons": reasons,
        "affected_surface": affected_surface,
        "dedup_key": dedup_key,
        "rate_limit_bucket": rate_limit["rate_limit_bucket"],
        "rate_limit_window_seconds": rate_limit_window_seconds,
        "would_suppress_duplicate": rate_limit["would_suppress_duplicate"],
        "would_repeat_critical": rate_limit["would_repeat_critical"],
        "previous_matching_preview_generated_at": rate_limit["previous_matching_preview_generated_at"],
        "telegram_preview_message": telegram_message,
        "operator_console_preview_message": console_message,
        "telegram_send_called": False,
        "telegram_message_sent": False,
        "recommended_next_operator_move": _recommended_next_operator_move(
            alert_required=alert_required,
            severity=severity,
            reasons=reasons,
        ),
        "recommended_r316_path": (
            RECOMMENDED_R316_SEND_GATE if severity == INFO_PREVIEW_NO_SEND else RECOMMENDED_R316_REPAIR
        ),
        "source_health_panel": source,
        "safety": safety,
        **safety,
    }
    safe_payload = _sanitize(payload)
    if should_write:
        append_record(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def evaluate_alert_reasons(
    health_panel: Mapping[str, Any],
    *,
    max_age_seconds: int,
) -> list[str]:
    timer = _mapping(health_panel.get("timer_summary"))
    lanes = _mapping(health_panel.get("lane_summary"))
    final = _mapping(health_panel.get("final_live_safety"))
    paper = _mapping(health_panel.get("paper_refresh_summary"))
    reasons: list[str] = []

    if health_panel.get("health_status") == HEALTH_BLOCKED:
        reasons.append("health_status_blocked")
    if timer.get("last_tick_recent") is False and _number(timer.get("last_tick_age_seconds")) > max_age_seconds:
        reasons.append("stale_observation_tick")
    if timer.get("timer_installed") is not True:
        reasons.append("timer_not_installed")
    if timer.get("timer_enabled") is not True:
        reasons.append("timer_not_enabled")
    if timer.get("timer_active") is not True:
        reasons.append("timer_not_active")
    if str(timer.get("service_last_exit_status") or "") not in {"", "0", "success"}:
        reasons.append("service_last_exit_status_not_zero")
    if lanes.get("all_primary_contracts_valid") is not True:
        reasons.append("primary_contract_invalid")
    if lanes.get("all_primary_observation_status_ok") is not True:
        reasons.append("primary_observation_status_not_ok")
    freshness = str(lanes.get("candidate_freshness_status") or "")
    if "CRITICAL" in freshness or freshness in {"FRESH_TRIGGER_CRITICAL", "CANDIDATE_FRESHNESS_CRITICAL"}:
        reasons.append("candidate_freshness_critical")
    if final.get("real_order_forbidden") is not True:
        reasons.append("final_live_safety_real_order_not_forbidden")
    if final.get("submit_allowed") is not False:
        reasons.append("final_live_safety_submit_allowed")
    if final.get("final_command_available") is not False:
        reasons.append("final_live_safety_final_command_available")
    baseline_lane = lanes.get("baseline_lane")
    armed_lane = final.get("armed_lane_key")
    if baseline_lane and armed_lane and baseline_lane != armed_lane:
        reasons.append("armed_lane_changed_unexpectedly")
    reasons.extend(_safety_flag_violations(health_panel))
    paper_health = paper.get("paper_refresh_health_status")
    failed_tasks = [str(task) for task in paper.get("last_failed_tasks") or []]
    if paper.get("fatal") is True or paper_health == PAPER_REFRESH_CRITICAL_FAILURE:
        reasons.append("paper_refresh_critical_failure")
    elif paper_health == PAPER_REFRESH_DEGRADED_NON_CRITICAL and set(failed_tasks) - {TASK_ETH_PAPER_OUTCOME}:
        reasons.append("paper_refresh_degraded_beyond_eth_paper_outcome")
    return _dedupe(reasons)


def build_dedup_key(
    *,
    severity: str,
    reasons: Sequence[str],
    affected_surface: Sequence[str],
) -> str:
    body = json.dumps(
        {
            "severity": severity,
            "reasons": sorted(str(reason) for reason in reasons),
            "affected_surface": sorted(str(surface) for surface in affected_surface),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "r315:" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]


def evaluate_rate_limit_preview(
    *,
    log_dir: str | Path,
    dedup_key: str,
    now: datetime,
    rate_limit_window_seconds: int,
    severity: str,
) -> dict[str, Any]:
    window = max(0, int(rate_limit_window_seconds))
    bucket = f"{dedup_key}:window_{window}s"
    previous_generated_at: str | None = None
    for record in load_multi_lane_observation_alerting_preview_records(log_dir=log_dir, limit=200):
        if record.get("dedup_key") != dedup_key:
            continue
        parsed = _parse_datetime(record.get("generated_at"))
        if parsed is None:
            continue
        age = (now - parsed).total_seconds()
        if 0 <= age <= window:
            previous_generated_at = parsed.isoformat()
            break
    duplicate = previous_generated_at is not None
    critical = severity == CRITICAL_PREVIEW_NO_SEND
    actionable = severity != INFO_PREVIEW_NO_SEND
    return {
        "rate_limit_bucket": bucket,
        "would_suppress_duplicate": bool(duplicate and actionable and not critical),
        "would_repeat_critical": bool(duplicate and critical),
        "previous_matching_preview_generated_at": previous_generated_at,
    }


def build_preview_message(
    health_panel: Mapping[str, Any],
    *,
    severity: str,
    reasons: Sequence[str],
    channel: str,
) -> str:
    timer = _mapping(health_panel.get("timer_summary"))
    final = _mapping(health_panel.get("final_live_safety"))
    reason_text = ", ".join(reasons) if reasons else "no actionable alert"
    action = _recommended_next_operator_move(
        alert_required=bool(reasons),
        severity=severity,
        reasons=reasons,
    )
    title = (
        "R315 Multi-Lane Observation Alert Preview"
        if channel == "telegram"
        else "R315 MULTI-LANE OBSERVATION ALERT PREVIEW"
    )
    return "\n".join(
        [
            title,
            f"severity: {severity}",
            f"reason: {reason_text}",
            f"last_tick_age_seconds: {timer.get('last_tick_age_seconds')}",
            (
                "timer: "
                f"installed={timer.get('timer_installed')} "
                f"enabled={timer.get('timer_enabled')} "
                f"active={timer.get('timer_active')} "
                f"service_exit={timer.get('service_last_exit_status')}"
            ),
            (
                "final_safety: "
                f"real_order_forbidden={final.get('real_order_forbidden')} "
                f"submit_allowed={final.get('submit_allowed')} "
                f"final_command_available={final.get('final_command_available')}"
            ),
            f"recommended_action: {action}",
            "telegram_send_called=false",
        ]
    )


def load_multi_lane_observation_alerting_preview_records(
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


def format_alerting_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), indent=2, sort_keys=True)


def format_alerting_preview_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R315 MULTI-LANE OBSERVATION ALERTING PREVIEW",
        "",
        "ALERT STATUS",
        f"alert_required: {payload.get('alert_required')}",
        "",
        "SEVERITY",
        f"alert_severity: {payload.get('alert_severity')}",
        "",
        "REASONS",
        f"alert_reasons: {_join(payload.get('alert_reasons'))}",
        "",
        "DEDUP/RATE LIMIT PREVIEW",
        f"dedup_key: {payload.get('dedup_key')}",
        f"rate_limit_bucket: {payload.get('rate_limit_bucket')}",
        f"rate_limit_window_seconds: {payload.get('rate_limit_window_seconds')}",
        f"would_suppress_duplicate: {payload.get('would_suppress_duplicate')}",
        f"would_repeat_critical: {payload.get('would_repeat_critical')}",
        "",
        "TELEGRAM PREVIEW MESSAGE",
        str(payload.get("telegram_preview_message") or ""),
        "",
        "OPERATOR CONSOLE PREVIEW MESSAGE",
        str(payload.get("operator_console_preview_message") or ""),
        "",
        "SAFETY FLAGS",
    ]
    for key in SAFETY:
        lines.append(f"{key}: {payload.get(key)}")
    lines.extend(
        [
            "",
            "RECOMMENDED NEXT PHASE",
            str(payload.get("recommended_r316_path")),
        ]
    )
    return "\n".join(lines)


def _severity(reasons: Sequence[str]) -> str:
    if not reasons:
        return INFO_PREVIEW_NO_SEND
    if any(reason in CRITICAL_REASONS or reason.startswith("safety_flag_") for reason in reasons):
        return CRITICAL_PREVIEW_NO_SEND
    return WARNING_PREVIEW_NO_SEND


def _affected_surface(reasons: Sequence[str]) -> list[str]:
    surfaces: list[str] = []
    for reason in reasons:
        if reason.startswith("timer_") or reason.startswith("stale_") or reason.startswith("service_"):
            surfaces.append("timer")
        elif reason.startswith("primary_") or reason.startswith("candidate_"):
            surfaces.append("lane_observation")
        elif reason.startswith("final_") or reason.startswith("armed_"):
            surfaces.append("final_live_safety")
        elif reason.startswith("paper_refresh_"):
            surfaces.append("paper_refresh")
        elif reason.startswith("safety_flag_"):
            surfaces.append("safety_flags")
        elif reason.startswith("health_status_"):
            surfaces.append("health_status")
        else:
            surfaces.append("observation_health")
    return _dedupe(surfaces)


def _recommended_next_operator_move(
    *,
    alert_required: bool,
    severity: str,
    reasons: Sequence[str],
) -> str:
    if not alert_required:
        return "continue_observation_no_send"
    if severity == CRITICAL_PREVIEW_NO_SEND:
        return "stop_and_repair_blocker_before_any_alert_send_gate"
    if "stale_observation_tick" in reasons or any(reason.startswith("timer_") for reason in reasons):
        return "inspect_observation_timer_and_recent_scheduler_tick"
    return "inspect_degraded_surface_before_r316_send_gate"


def _safety_flag_violations(health_panel: Mapping[str, Any]) -> list[str]:
    safety_payload = _mapping(health_panel.get("safety"))
    reasons: list[str] = []
    for key, expected in SAFETY.items():
        observed = health_panel.get(key, safety_payload.get(key, expected))
        if observed is not expected:
            reasons.append(f"safety_flag_{key}_unexpected")
    return reasons


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
        prog="python -m src.app.hammer_radar.operator.multi_lane_observation_alerting_preview"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--max-age-seconds", type=int, default=180)
    parser.add_argument("--rate-limit-window-seconds", type=int, default=DEFAULT_RATE_LIMIT_WINDOW_SECONDS)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    payload = build_multi_lane_observation_alerting_preview(
        log_dir=args.log_dir,
        max_age_seconds=args.max_age_seconds,
        no_write=args.no_write,
        rate_limit_window_seconds=args.rate_limit_window_seconds,
    )
    if args.json and not args.text:
        print(format_alerting_preview_json(payload))
    else:
        print(format_alerting_preview_text(payload))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint.
    raise SystemExit(main())
