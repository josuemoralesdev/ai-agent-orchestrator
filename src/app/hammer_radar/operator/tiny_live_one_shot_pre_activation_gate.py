"""R285 one-shot tiny-live pre-activation gate packet.

This surface is read-only/no-submit. It can compose already-safe Binance
readiness checks, exact-lane strategy candidate watch state, risk contracts,
autonomous dry-run state, and local audit ledgers into a single operator packet.
It never creates executable order payloads, exposes a final submit command,
places orders, changes Binance settings, writes lane controls, or enables live.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.strategy_promotion_watcher import (
    WATCH_BLOCKED_NEAR_MISS,
    WATCH_BLOCKED_PAPER_ONLY,
    WATCH_FOUND,
    WATCH_WAIT,
    build_live_qualified_fresh_candidate_watch,
)
from src.app.hammer_radar.operator.tiny_live_actual_submit_gate import (
    load_tiny_live_actual_submit_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_autonomous_armed_dry_run import (
    CONFIG_PATH as AUTONOMOUS_ARMING_CONFIG_PATH,
    build_autonomous_dry_run_arming_status,
    build_simulated_order_triplet,
    load_autonomous_arming_state,
)
from src.app.hammer_radar.operator.tiny_live_binance_autonomous_readiness_binding import (
    BINANCE_READINESS_READY,
    build_tiny_live_binance_autonomous_readiness_binding,
    load_latest_binance_autonomous_readiness_binding,
)
from src.app.hammer_radar.operator.tiny_live_leverage_margin_readiness import (
    LEVERAGE_MARGIN_READY,
    POST_MANUAL_LEVERAGE_MARGIN_VERIFIED,
    build_post_manual_leverage_margin_alignment_verification,
    load_latest_post_manual_leverage_margin_verification,
)
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import (
    LIVE_QUALIFIED,
    NEAR_MISS_INCUBATOR,
    PAPER_ONLY,
    build_exact_lane_risk_contract_status,
)

EVENT_TYPE = "TINY_LIVE_ONE_SHOT_PRE_ACTIVATION_GATE"
CREATED_BY_PHASE = "R285_ONE_SHOT_TINY_LIVE_PRE_ACTIVATION_GATE_PACKET"
LEDGER_FILENAME = "tiny_live_one_shot_pre_activation_gate.ndjson"

ONE_SHOT_PRE_ACTIVATION_READY_TO_WAIT_FOR_TRIGGER = (
    "ONE_SHOT_PRE_ACTIVATION_READY_TO_WAIT_FOR_TRIGGER"
)
ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER = (
    "ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER"
)
ONE_SHOT_PRE_ACTIVATION_BLOCKED = "ONE_SHOT_PRE_ACTIVATION_BLOCKED"
ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED = "ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED"

WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE = "WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE"
RUN_ONE_SHOT_DRY_RUN_TRIGGER_PACKET_OR_ARMING_REVIEW = (
    "RUN_ONE_SHOT_DRY_RUN_TRIGGER_PACKET_OR_ARMING_REVIEW"
)
RUN_READONLY_PRE_ACTIVATION_CHECKS = "RUN_READONLY_PRE_ACTIVATION_CHECKS"
CLEAR_PRE_ACTIVATION_BLOCKERS = "CLEAR_PRE_ACTIVATION_BLOCKERS"

APPROVED_LIVE_QUALIFIED_LANES = {
    "BTCUSDT|44m|long|ladder_close_50_618",
    "BTCUSDT|44m|short|ladder_close_50_618",
    "BTCUSDT|55m|long|ladder_close_50_618",
}
OPERATOR_ROLE = "arms_disarms_tunes_risk_not_per_signal_approval"
MACHINE_ROLE = "auto_triggers_when_armed_and_all_gates_open"

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_controls_written": False,
    "live_config_written": False,
    "risk_contract_mutated": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "final_command_available": False,
    "submit_allowed": False,
    "submit_attempted": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "leverage_change_called": False,
    "margin_change_called": False,
    "mutation_performed": False,
    "signed_trading_request_created": False,
    "signed_order_request_created": False,
    "signed_request_created": False,
    "signed_url_shown": False,
    "signature_shown": False,
    "secrets_shown": False,
    "secret_values_in_output": False,
    "kill_switch_disabled": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "real_order_forbidden": True,
}


def build_tiny_live_one_shot_pre_activation_gate(
    *,
    log_dir: str | Path | None = None,
    fetch_binance_readonly_precision_mark_price: bool = False,
    confirm_tiny_live_binance_readonly_fetch: str | None = None,
    fetch_binance_readonly_account_position: bool = False,
    confirm_binance_readonly_account_position: str | None = None,
    load_discovered_binance_readonly_env: bool = False,
    binance_readonly_env_file: str | Path | None = None,
    record_pre_activation_review: bool = False,
    operator_id: str = "local_operator",
    reason: str | None = None,
    risk_contract_config_path: str | Path | None = None,
    autonomous_arming_config_path: str | Path | None = None,
    candidate_watch: Mapping[str, Any] | None = None,
    binance_readiness: Mapping[str, Any] | None = None,
    post_manual_verification: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
    urlopen_func: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else None
    arming_path = (
        Path(autonomous_arming_config_path)
        if autonomous_arming_config_path is not None
        else AUTONOMOUS_ARMING_CONFIG_PATH
    )
    fetch_requested = bool(
        fetch_binance_readonly_precision_mark_price
        or fetch_binance_readonly_account_position
        or load_discovered_binance_readonly_env
        or binance_readonly_env_file is not None
    )

    binance = dict(binance_readiness or {})
    if not binance:
        if fetch_requested:
            binance = build_tiny_live_binance_autonomous_readiness_binding(
                log_dir=resolved_log_dir,
                fetch_binance_readonly_precision_mark_price=fetch_binance_readonly_precision_mark_price,
                confirm_tiny_live_binance_readonly_fetch=confirm_tiny_live_binance_readonly_fetch,
                fetch_binance_readonly_account_position=fetch_binance_readonly_account_position,
                confirm_binance_readonly_account_position=confirm_binance_readonly_account_position,
                load_discovered_binance_readonly_env=load_discovered_binance_readonly_env,
                binance_readonly_env_file=binance_readonly_env_file,
                risk_contract_config_path=risk_path,
                autonomous_arming_config_path=arming_path,
                env=env,
                now=generated_at,
                urlopen_func=urlopen_func,
            )
        else:
            binance = load_latest_binance_autonomous_readiness_binding(log_dir=resolved_log_dir)

    post_manual = dict(post_manual_verification or {})
    if not post_manual:
        if fetch_binance_readonly_account_position:
            post_manual = build_post_manual_leverage_margin_alignment_verification(
                log_dir=resolved_log_dir,
                fetch_binance_readonly_account_position=fetch_binance_readonly_account_position,
                confirm_binance_readonly_account_position=confirm_binance_readonly_account_position,
                load_discovered_binance_readonly_env=load_discovered_binance_readonly_env,
                binance_readonly_env_file=binance_readonly_env_file,
                risk_contract_config_path=risk_path,
                env=env,
                now=generated_at,
                urlopen_func=urlopen_func,
            )
        else:
            post_manual = load_latest_post_manual_leverage_margin_verification(log_dir=resolved_log_dir)

    watch = dict(candidate_watch or build_live_qualified_fresh_candidate_watch(log_dir=resolved_log_dir))
    arming_state = load_autonomous_arming_state(arming_path)
    arming_status = build_autonomous_dry_run_arming_status(
        config_path=arming_path,
        log_dir=resolved_log_dir,
    )

    candidate = _current_candidate(watch)
    evidence = _strategy_evidence(watch)
    lane_key = str(candidate.get("lane_key") or _watch_current_lane(watch) or "")
    signal_id = str(candidate.get("signal_id") or "")
    watch_status = str(_candidate_alert(watch).get("status") or watch.get("status") or WATCH_WAIT)
    live_class = str(evidence.get("live_qualification_class") or evidence.get("watch_category") or "")
    live_qualified_lanes = _lane_keys(watch.get("live_qualified_lanes"))
    approved_lane_match = bool(lane_key and lane_key in APPROVED_LIVE_QUALIFIED_LANES)
    fresh_candidate_exists = bool(candidate)
    fresh_candidate_live_qualified = watch_status == WATCH_FOUND and live_class == LIVE_QUALIFIED

    risk_contract = (
        build_exact_lane_risk_contract_status(
            lane_key=lane_key,
            risk_contract_config_path=risk_path,
            strategy_qualification={"strategy_qualified": fresh_candidate_live_qualified},
        )
        if lane_key
        else _empty_risk_contract_status(risk_path)
    )
    risk_contract_blockers = _risk_contract_blockers(risk_contract)
    exact_lane_risk_contract_valid = (
        risk_contract.get("risk_contract_valid") is True and not risk_contract_blockers
    )

    protective_preview = _protective_preview(
        candidate=candidate,
        arming_state=arming_state,
        risk_contract=risk_contract,
    )
    idempotency = _idempotency_summary(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        signal_id=signal_id,
    )

    matrix = _readiness_matrix(
        binance=binance,
        post_manual=post_manual,
        watch=watch,
        arming_state=arming_state,
        live_qualified_lanes=live_qualified_lanes,
        candidate=candidate,
        evidence=evidence,
        watch_status=watch_status,
        lane_key=lane_key,
        signal_id=signal_id,
        approved_lane_match=approved_lane_match,
        risk_contract=risk_contract,
        exact_lane_risk_contract_valid=exact_lane_risk_contract_valid,
        protective_preview=protective_preview,
        idempotency=idempotency,
    )
    blockers = _blockers(
        matrix=matrix,
        fresh_candidate_exists=fresh_candidate_exists,
        watch_status=watch_status,
        live_class=live_class,
        risk_contract_blockers=risk_contract_blockers,
        risk_contract=risk_contract,
        protective_preview=protective_preview,
        idempotency=idempotency,
        fetch_requested=fetch_requested,
        binance=binance,
        post_manual=post_manual,
    )
    status = _status(matrix=matrix, blockers=blockers, fetch_requested=fetch_requested, binance=binance, post_manual=post_manual)
    next_required_step = _next_required_step(status)
    safety = _merged_safety(binance, post_manual, watch)
    panel = _panel(
        status=status,
        matrix=matrix,
        blockers=blockers,
        watch=watch,
        binance=binance,
        post_manual=post_manual,
        risk_contract=risk_contract,
        protective_preview=protective_preview,
        idempotency=idempotency,
        next_required_step=next_required_step,
    )

    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "created_by_phase": CREATED_BY_PHASE,
            "generated_at": generated_at.isoformat(),
            "operator_role": OPERATOR_ROLE,
            "machine_role": MACHINE_ROLE,
            "per_signal_operator_approval_required": False,
            "alert_is_visibility_only": True,
            "status": status,
            "next_required_step": next_required_step,
            "record_pre_activation_review_requested": bool(record_pre_activation_review),
            "pre_activation_review_recorded": False,
            "operator_intent": {
                "operator_id": str(operator_id or "local_operator"),
                "reason": str(reason or ""),
                "record_only": True,
            },
            "approved_live_qualified_lanes": sorted(APPROVED_LIVE_QUALIFIED_LANES),
            "readiness_matrix": matrix,
            **matrix,
            "candidate_watch_status": watch_status,
            "candidate_watch": watch,
            "binance_readiness": binance,
            "post_manual_leverage_margin_verification": post_manual,
            "autonomous_dry_run_arming_status": arming_status,
            "exact_lane_risk_contract": risk_contract,
            "protective_triplet_preview": protective_preview,
            "idempotency_summary": idempotency,
            "blockers": blockers,
            "one_shot_live_allowed": False,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "safe_next_cli_command": safe_one_shot_pre_activation_gate_cli_command(),
            "one_shot_pre_activation_gate_panel": panel,
            "safety": safety,
            "source_surfaces_used": [
                "src/app/hammer_radar/operator/tiny_live_binance_autonomous_readiness_binding.py",
                "src/app/hammer_radar/operator/tiny_live_leverage_margin_readiness.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_armed_dry_run.py",
                "src/app/hammer_radar/operator/strategy_promotion_watcher.py",
                "configs/hammer_radar/tiny_live_risk_contracts.json",
                "configs/hammer_radar/autonomous_arming_state.json",
                f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
            ],
        }
    )
    if record_pre_activation_review:
        payload = append_tiny_live_one_shot_pre_activation_gate(payload, log_dir=resolved_log_dir)
    return payload


def load_latest_tiny_live_one_shot_pre_activation_gate(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    records = load_tiny_live_one_shot_pre_activation_gate_records(log_dir=log_dir, limit=1)
    return records[0] if records else {}


def load_tiny_live_one_shot_pre_activation_gate_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_one_shot_pre_activation_gate_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=8_388_608)]


def append_tiny_live_one_shot_pre_activation_gate(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    payload = _sanitize(
        {
            **dict(record),
            "pre_activation_review_record_id": record.get("pre_activation_review_record_id")
            or f"r285_one_shot_pre_activation_{uuid4().hex}",
            "pre_activation_review_recorded": True,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    )
    path = tiny_live_one_shot_pre_activation_gate_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def tiny_live_one_shot_pre_activation_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_one_shot_pre_activation_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def safe_one_shot_pre_activation_gate_cli_command() -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward tiny-live-one-shot-pre-activation-gate "
        "--load-discovered-binance-readonly-env "
        "--fetch-binance-readonly-precision-mark-price "
        "--confirm-tiny-live-binance-readonly-fetch "
        "\"I CONFIRM BINANCE READONLY PRECISION MARK PRICE CHECK ONLY; NO ORDER; NO SIGNATURE; NO PRIVATE ENDPOINT.\" "
        "--fetch-binance-readonly-account-position "
        "--confirm-binance-readonly-account-position "
        "\"I CONFIRM BINANCE READONLY ACCOUNT POSITION CHECK ONLY; NO ORDER; NO TEST ORDER; NO LEVERAGE CHANGE; NO MARGIN CHANGE.\" "
        "--record-pre-activation-review "
        "--operator-id local_operator "
        "--reason \"R285 no-submit pre-activation review; wait for fresh LIVE_QUALIFIED candidate.\""
    )


def build_not_checked_pre_activation_gate_packet(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    latest = load_latest_tiny_live_one_shot_pre_activation_gate(log_dir=log_dir)
    if latest:
        latest["final_command_available"] = False
        latest["submit_allowed"] = False
        latest["real_order_forbidden"] = True
        latest["safety"] = _merged_safety(latest)
        return _sanitize(latest)
    generated_at = datetime.now(UTC)
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "generated_at": generated_at.isoformat(),
        "operator_role": OPERATOR_ROLE,
        "machine_role": MACHINE_ROLE,
        "per_signal_operator_approval_required": False,
        "alert_is_visibility_only": True,
        "status": ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED,
        "next_required_step": RUN_READONLY_PRE_ACTIVATION_CHECKS,
        "blockers": ["pre_activation_gate_not_checked"],
        "safe_next_cli_command": safe_one_shot_pre_activation_gate_cli_command(),
        "one_shot_live_allowed": False,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "safety": dict(SAFETY),
    }
    payload["one_shot_pre_activation_gate_panel"] = _panel(
        status=payload["status"],
        matrix={},
        blockers=payload["blockers"],
        watch={},
        binance={},
        post_manual={},
        risk_contract={},
        protective_preview={},
        idempotency={},
        next_required_step=payload["next_required_step"],
    )
    return _sanitize(payload)


def _readiness_matrix(
    *,
    binance: Mapping[str, Any],
    post_manual: Mapping[str, Any],
    watch: Mapping[str, Any],
    arming_state: Mapping[str, Any],
    live_qualified_lanes: list[str],
    candidate: Mapping[str, Any],
    evidence: Mapping[str, Any],
    watch_status: str,
    lane_key: str,
    signal_id: str,
    approved_lane_match: bool,
    risk_contract: Mapping[str, Any],
    exact_lane_risk_contract_valid: bool,
    protective_preview: Mapping[str, Any],
    idempotency: Mapping[str, Any],
) -> dict[str, Any]:
    binance_matrix = binance.get("autonomous_one_shot_readiness_matrix") if isinstance(binance.get("autonomous_one_shot_readiness_matrix"), Mapping) else {}
    current_live_class = str(evidence.get("live_qualification_class") or evidence.get("watch_category") or "")
    contract = risk_contract.get("contract") if isinstance(risk_contract.get("contract"), Mapping) else {}
    return {
        "binance_readiness_ready": binance.get("status") == BINANCE_READINESS_READY
        or binance_matrix.get("binance_readiness_ready") is True,
        "exchange_minimum_ready": binance_matrix.get("exchange_minimum_ready") is True
        or binance.get("cap_clears_exchange_minimum") is True,
        "wallet_ready": binance_matrix.get("wallet_ready") is True
        or binance.get("wallet_supports_minimum_tiny") is True,
        "wallet_supports_configured_margin_budget": (
            binance.get("wallet_supports_configured_margin_budget") is True
            or post_manual.get("wallet_supports_configured_margin_budget") is True
        ),
        "no_conflicting_position": (
            binance_matrix.get("no_conflicting_position") is True
            or binance.get("open_position_conflict") is False
            or post_manual.get("open_position_conflict") is False
        ),
        "leverage_margin_ready": (
            binance.get("leverage_margin_ready") is True
            or post_manual.get("leverage_margin_ready") is True
            or post_manual.get("leverage_margin_status") == LEVERAGE_MARGIN_READY
        ),
        "post_manual_leverage_margin_verified": (
            post_manual.get("status") == POST_MANUAL_LEVERAGE_MARGIN_VERIFIED
            or post_manual.get("post_manual_alignment_verified") is True
        ),
        "live_qualified_lanes_available": bool(live_qualified_lanes),
        "current_fresh_candidate_exists": bool(candidate),
        "current_fresh_candidate_is_live_qualified": (
            bool(candidate) and watch_status == WATCH_FOUND and current_live_class == LIVE_QUALIFIED
        ),
        "current_candidate_lane_key": lane_key or None,
        "current_candidate_signal_id": signal_id or None,
        "approved_lane_match": approved_lane_match,
        "exact_lane_risk_contract_found": risk_contract.get("exact_contract_found") is True,
        "exact_lane_risk_contract_valid": exact_lane_risk_contract_valid,
        "risk_contract_notional_cap_usdt": _number(
            contract.get("max_position_notional_usdt") or contract.get("max_notional_usdt")
        ),
        "risk_contract_leverage": _number(contract.get("leverage")),
        "risk_contract_margin_budget_usdt": _number(
            contract.get("margin_budget_usdt") or contract.get("tiny_live_margin_usdt")
        ),
        "protective_orders_required": (
            contract.get("protective_stop_required") is True and contract.get("take_profit_required") is True
        ),
        "protective_triplet_preview_available": protective_preview.get("available") is True,
        "protective_triplet_preview_valid": protective_preview.get("valid") is True,
        "idempotency_clean": idempotency.get("idempotency_clean") is True,
        "no_prior_live_submit": idempotency.get("no_prior_live_submit") is True,
        "autonomous_dry_run_default_off": (
            arming_state.get("global_auto_live_enabled") is not True
            and arming_state.get("armed_lane_key") in {None, ""}
            and not arming_state.get("lane_auto_live_enabled_keys")
        ),
        "global_auto_live_enabled": arming_state.get("global_auto_live_enabled") is True,
        "exact_lane_auto_armed": bool(
            lane_key
            and arming_state.get("global_auto_live_enabled") is True
            and arming_state.get("armed_lane_key") == lane_key
            and lane_key in set(arming_state.get("allowed_lane_keys") or [])
            and lane_key in set(arming_state.get("lane_auto_live_enabled_keys") or [])
        ),
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def _blockers(
    *,
    matrix: Mapping[str, Any],
    fresh_candidate_exists: bool,
    watch_status: str,
    live_class: str,
    risk_contract_blockers: list[str],
    risk_contract: Mapping[str, Any],
    protective_preview: Mapping[str, Any],
    idempotency: Mapping[str, Any],
    fetch_requested: bool,
    binance: Mapping[str, Any],
    post_manual: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    for key in (
        "binance_readiness_ready",
        "exchange_minimum_ready",
        "wallet_ready",
        "wallet_supports_configured_margin_budget",
        "no_conflicting_position",
        "leverage_margin_ready",
        "post_manual_leverage_margin_verified",
        "live_qualified_lanes_available",
    ):
        if matrix.get(key) is not True:
            blockers.append(key.replace("_ready", "_not_ready").replace("_verified", "_not_verified"))
    if not fetch_requested and not binance and not post_manual:
        blockers.append("pre_activation_gate_not_checked")
    if fresh_candidate_exists:
        if watch_status == WATCH_BLOCKED_PAPER_ONLY or live_class == PAPER_ONLY:
            blockers.extend(["strategy_not_live_qualified", "paper_only"])
        if watch_status == WATCH_BLOCKED_NEAR_MISS or live_class == NEAR_MISS_INCUBATOR:
            blockers.extend(["strategy_not_live_qualified", "near_miss"])
        if matrix.get("current_fresh_candidate_is_live_qualified") is not True:
            blockers.append("current_candidate_not_live_qualified")
        if matrix.get("approved_lane_match") is not True:
            blockers.append("candidate_lane_not_approved_for_r285")
        if risk_contract.get("exact_contract_found") is not True:
            blockers.append("exact_lane_risk_contract_missing")
        elif matrix.get("exact_lane_risk_contract_valid") is not True:
            blockers.append("exact_lane_risk_contract_invalid")
        blockers.extend(risk_contract_blockers)
        if matrix.get("protective_orders_required") is not True:
            blockers.append("protective_orders_not_required_by_contract")
        if protective_preview.get("available") is not True:
            blockers.append("protective_triplet_preview_missing")
        elif protective_preview.get("valid") is not True:
            blockers.extend(str(item) for item in protective_preview.get("blockers") or ["protective_triplet_preview_invalid"])
        if idempotency.get("idempotency_clean") is not True:
            blockers.append("idempotency_not_clean")
        if idempotency.get("no_prior_live_submit") is not True:
            blockers.append("prior_live_submit_found")
    return _dedupe(blockers)


def _status(
    *,
    matrix: Mapping[str, Any],
    blockers: list[str],
    fetch_requested: bool,
    binance: Mapping[str, Any],
    post_manual: Mapping[str, Any],
) -> str:
    required_pre_candidate = [
        "binance_readiness_ready",
        "exchange_minimum_ready",
        "wallet_ready",
        "wallet_supports_configured_margin_budget",
        "no_conflicting_position",
        "leverage_margin_ready",
        "post_manual_leverage_margin_verified",
        "live_qualified_lanes_available",
    ]
    if not fetch_requested and not binance and not post_manual:
        return ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED
    if not all(matrix.get(key) is True for key in required_pre_candidate):
        return ONE_SHOT_PRE_ACTIVATION_BLOCKED
    if matrix.get("current_fresh_candidate_exists") is not True:
        return ONE_SHOT_PRE_ACTIVATION_READY_TO_WAIT_FOR_TRIGGER
    dry_run_ready_keys = [
        "current_fresh_candidate_is_live_qualified",
        "approved_lane_match",
        "exact_lane_risk_contract_found",
        "exact_lane_risk_contract_valid",
        "protective_orders_required",
        "protective_triplet_preview_available",
        "protective_triplet_preview_valid",
        "idempotency_clean",
        "no_prior_live_submit",
    ]
    if all(matrix.get(key) is True for key in dry_run_ready_keys):
        return ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER
    return ONE_SHOT_PRE_ACTIVATION_BLOCKED


def _next_required_step(status: str) -> str:
    if status == ONE_SHOT_PRE_ACTIVATION_READY_TO_WAIT_FOR_TRIGGER:
        return WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE
    if status == ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER:
        return RUN_ONE_SHOT_DRY_RUN_TRIGGER_PACKET_OR_ARMING_REVIEW
    if status == ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED:
        return RUN_READONLY_PRE_ACTIVATION_CHECKS
    return CLEAR_PRE_ACTIVATION_BLOCKERS


def _risk_contract_blockers(risk_contract: Mapping[str, Any]) -> list[str]:
    contract = risk_contract.get("contract") if isinstance(risk_contract.get("contract"), Mapping) else {}
    blockers = [str(item) for item in risk_contract.get("blocked_by") or []]
    if not contract:
        return _dedupe(blockers)
    if contract.get("tiny_live_contract_mode") != "explicit_notional_cap_with_leverage":
        blockers.append("risk_contract_mode_not_explicit_notional_cap_with_leverage")
    if _number(contract.get("max_position_notional_usdt") or contract.get("max_notional_usdt")) != 80.0:
        blockers.append("risk_contract_notional_cap_not_80")
    if _number(contract.get("leverage")) != 10.0:
        blockers.append("risk_contract_leverage_not_10")
    if _number(contract.get("margin_budget_usdt") or contract.get("tiny_live_margin_usdt")) != 8.0:
        blockers.append("risk_contract_margin_budget_not_8")
    if contract.get("max_loss_usdt") is None:
        blockers.append("risk_contract_max_loss_missing")
    if contract.get("protective_stop_required") is not True or contract.get("take_profit_required") is not True:
        blockers.append("protective_orders_not_required_by_contract")
    return _dedupe(blockers)


def _protective_preview(
    *,
    candidate: Mapping[str, Any],
    arming_state: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
) -> dict[str, Any]:
    if not candidate:
        return {
            "available": False,
            "valid": False,
            "reason": "no_current_fresh_candidate",
            "order_payload_created": False,
            "executable_payload_created": False,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    missing = [
        key
        for key in ("entry", "stop", "take_profit", "symbol", "direction", "lane_key")
        if candidate.get(key) in {None, ""}
    ]
    if missing:
        return {
            "available": False,
            "valid": False,
            "blockers": [f"candidate_{key}_missing" for key in missing],
            "order_payload_created": False,
            "executable_payload_created": False,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    contract = risk_contract.get("contract") if isinstance(risk_contract.get("contract"), Mapping) else {}
    preview_state = {
        **dict(arming_state),
        "max_position_notional_usdt": 80.0,
        "leverage": 10.0,
        "require_protective_orders": True,
    }
    if contract:
        preview_state["max_position_notional_usdt"] = (
            contract.get("max_position_notional_usdt") or contract.get("max_notional_usdt") or 80.0
        )
        preview_state["leverage"] = contract.get("leverage") or 10.0
    triplet = build_simulated_order_triplet(selected_candidate=candidate, arming_state=preview_state)
    blockers: list[str] = []
    for key in ("entry_order", "protective_stop_order", "take_profit_order"):
        order = triplet.get(key) if isinstance(triplet.get(key), Mapping) else {}
        if order.get("submit_allowed") is not False:
            blockers.append(f"{key}_submit_allowed_not_false")
        if order.get("real_order_forbidden") is not True:
            blockers.append(f"{key}_real_order_forbidden_not_true")
    if triplet.get("binance_order_endpoint_called") is not False:
        blockers.append("triplet_binance_order_endpoint_called")
    if triplet.get("binance_test_order_endpoint_called") is not False:
        blockers.append("triplet_binance_test_order_endpoint_called")
    return _sanitize(
        {
            "available": not blockers,
            "valid": not blockers,
            "triplet": triplet,
            "blockers": _dedupe(blockers),
            "order_payload_created": False,
            "executable_payload_created": False,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    )


def _idempotency_summary(*, log_dir: Path, lane_key: str, signal_id: str) -> dict[str, Any]:
    prior = False
    for record in load_tiny_live_actual_submit_gate_records(log_dir=log_dir, limit=0):
        if record.get("actual_submit_executed") is not True:
            continue
        text = json.dumps(record, sort_keys=True, default=str)
        if (signal_id and signal_id in text) or (lane_key and lane_key in text):
            prior = True
            break
    return {
        "lane_key": lane_key or None,
        "signal_id": signal_id or None,
        "prior_live_submit_found": prior,
        "no_prior_live_submit": not prior,
        "idempotency_clean": not prior,
    }


def _panel(
    *,
    status: str,
    matrix: Mapping[str, Any],
    blockers: list[str],
    watch: Mapping[str, Any],
    binance: Mapping[str, Any],
    post_manual: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    protective_preview: Mapping[str, Any],
    idempotency: Mapping[str, Any],
    next_required_step: str,
) -> dict[str, Any]:
    candidate = _current_candidate(watch)
    return _sanitize(
        {
            "operator_role": OPERATOR_ROLE,
            "machine_role": MACHINE_ROLE,
            "per_signal_operator_approval_required": False,
            "alert_is_visibility_only": True,
            "status": status,
            "current_candidate_status": _candidate_alert(watch).get("status")
            or watch.get("status")
            or WATCH_WAIT,
            "current_candidate_lane_key": matrix.get("current_candidate_lane_key"),
            "current_candidate_signal_id": matrix.get("current_candidate_signal_id"),
            "binance_readiness_summary": {
                "status": binance.get("status"),
                "binance_readiness_ready": matrix.get("binance_readiness_ready"),
                "exchange_minimum_ready": matrix.get("exchange_minimum_ready"),
                "wallet_ready": matrix.get("wallet_ready"),
                "wallet_supports_configured_margin_budget": matrix.get(
                    "wallet_supports_configured_margin_budget"
                ),
                "no_conflicting_position": matrix.get("no_conflicting_position"),
            },
            "leverage_margin_verified_summary": {
                "status": post_manual.get("status"),
                "leverage_margin_ready": matrix.get("leverage_margin_ready"),
                "post_manual_leverage_margin_verified": matrix.get(
                    "post_manual_leverage_margin_verified"
                ),
                "current_leverage": post_manual.get("current_leverage")
                or binance.get("current_leverage"),
                "current_margin_mode": post_manual.get("current_margin_mode")
                or binance.get("current_margin_mode"),
            },
            "live_qualified_lane_list": _lane_keys(watch.get("live_qualified_lanes")),
            "approved_lane_match": matrix.get("approved_lane_match"),
            "exact_risk_contract_status": {
                "found": matrix.get("exact_lane_risk_contract_found"),
                "valid": matrix.get("exact_lane_risk_contract_valid"),
                "blocked_by": list(risk_contract.get("blocked_by") or []),
                "no_cross_lane_borrowing": risk_contract.get("no_cross_lane_borrowing") is True,
            },
            "protective_preview_status": {
                "available": protective_preview.get("available") is True,
                "valid": protective_preview.get("valid") is True,
                "blockers": list(protective_preview.get("blockers") or []),
            },
            "idempotency_status": idempotency,
            "candidate": candidate or None,
            "blockers": blockers,
            "next_required_step": next_required_step,
            "safe_next_cli_command": safe_one_shot_pre_activation_gate_cli_command(),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    )


def _current_candidate(watch: Mapping[str, Any]) -> dict[str, Any]:
    alert = _candidate_alert(watch)
    candidate = alert.get("current_candidate")
    return dict(candidate) if isinstance(candidate, Mapping) else {}


def _strategy_evidence(watch: Mapping[str, Any]) -> dict[str, Any]:
    alert = _candidate_alert(watch)
    evidence = alert.get("strategy_evidence")
    return dict(evidence) if isinstance(evidence, Mapping) else {}


def _candidate_alert(watch: Mapping[str, Any]) -> dict[str, Any]:
    alert = watch.get("candidate_alert_packet")
    return dict(alert) if isinstance(alert, Mapping) else {}


def _watch_current_lane(watch: Mapping[str, Any]) -> str:
    fresh = watch.get("current_fresh_candidate_status")
    if isinstance(fresh, Mapping):
        return str(fresh.get("current_candidate_lane_key") or "")
    return ""


def _lane_keys(rows: Any) -> list[str]:
    keys: list[str] = []
    for row in rows or []:
        if isinstance(row, Mapping):
            key = str(row.get("strategy_key") or row.get("lane_key") or "")
            if key:
                keys.append(key)
        elif row:
            keys.append(str(row))
    return sorted(set(keys))


def _empty_risk_contract_status(risk_path: Path | None) -> dict[str, Any]:
    return {
        **dict(SAFETY),
        "lane_key": None,
        "risk_contract_path": str(risk_path) if risk_path else None,
        "exact_contract_found": False,
        "risk_contract_valid": False,
        "contract": {},
        "validation_summary": {},
        "blocked_by": ["no_current_candidate_lane"],
        "no_cross_lane_borrowing": True,
    }


def _merged_safety(*surfaces: Mapping[str, Any]) -> dict[str, Any]:
    safety = dict(SAFETY)
    for surface in surfaces:
        source = surface.get("safety") if isinstance(surface.get("safety"), Mapping) else surface
        for key in list(safety):
            if key in source:
                if safety[key] is False:
                    safety[key] = source.get(key) is True
                elif safety[key] is True:
                    safety[key] = source.get(key) is not False
    safety.update(
        {
            "order_payload_created": False,
            "executable_payload_created": False,
            "final_command_available": False,
            "submit_allowed": False,
            "submit_attempted": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "leverage_change_called": False,
            "margin_change_called": False,
            "mutation_performed": False,
            "signed_trading_request_created": False,
            "signed_order_request_created": False,
            "signed_url_shown": False,
            "signature_shown": False,
            "secrets_shown": False,
            "secret_values_in_output": False,
            "real_order_forbidden": True,
            "paper_live_separation_intact": True,
        }
    )
    return safety


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            text = str(key).lower()
            if "secret" in text and key not in {"secrets_shown", "secret_values_in_output", "loaded_secret_names_redacted"}:
                clean[key] = "***REDACTED***" if item else item
                continue
            if "signature" in text and key not in {
                "signature_shown",
                "signed_order_request_created",
                "signed_trading_request_created",
                "signed_request_created",
            }:
                clean[key] = "***REDACTED***" if item else item
                continue
            clean[str(key)] = _sanitize(item)
        return clean
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
