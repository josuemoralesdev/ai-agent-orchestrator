"""R96 betrayal true paper tracking scaffold.

This module turns current betrayal audit candidates into deterministic paper
tracking identities. It declares future outcome schema and ledger paths only;
it never fabricates outcomes, creates executable payloads, calls Binance,
checks balances, mutates env files, or enables live execution.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_strategy_audit import (
    BETRAYAL_PRIMARY_CANDIDATE,
    BETRAYAL_WATCHLIST,
    build_betrayal_strategy_audit,
)

PHASE = "R96"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "BETRAYAL_TRUE_PAPER_TRACKING_SCAFFOLD_ONLY_NO_ORDER"
REPORT_FILENAME = "betrayal_true_paper_tracking_scaffold.json"
OUTCOMES_FILENAME = "betrayal_true_paper_outcomes.ndjson"

BETRAYAL_TRUE_PAPER_SCAFFOLD_ONLY = "BETRAYAL_TRUE_PAPER_SCAFFOLD_ONLY"
BETRAYAL_AUDIT_CANDIDATES_FOUND = "BETRAYAL_AUDIT_CANDIDATES_FOUND"
BETRAYAL_PAPER_IDENTITIES_CREATED = "BETRAYAL_PAPER_IDENTITIES_CREATED"
BETRAYAL_OUTCOME_LEDGER_DECLARED = "BETRAYAL_OUTCOME_LEDGER_DECLARED"
BETRAYAL_TRUE_PAPER_OUTCOMES_REQUIRED = "BETRAYAL_TRUE_PAPER_OUTCOMES_REQUIRED"
BETRAYAL_MINIMUM_SAMPLE_REQUIREMENTS_DECLARED = "BETRAYAL_MINIMUM_SAMPLE_REQUIREMENTS_DECLARED"
BETRAYAL_NOT_LIVE_READY = "BETRAYAL_NOT_LIVE_READY"
BETRAYAL_NON_EXECUTABLE_ONLY = "BETRAYAL_NON_EXECUTABLE_ONLY"

AUDIT_ONLY = "AUDIT_ONLY"
PAPER_IDENTITY_CREATED = "PAPER_IDENTITY_CREATED"
PAPER_TRACKING_READY = "PAPER_TRACKING_READY"
PAPER_OUTCOMES_PENDING = "PAPER_OUTCOMES_PENDING"
PAPER_EVIDENCE_INSUFFICIENT = "PAPER_EVIDENCE_INSUFFICIENT"
PAPER_READY_FOR_REVIEW = "PAPER_READY_FOR_REVIEW"
LIVE_READY_FALSE = "LIVE_READY_FALSE"
NAIVE_INVERSE_AUDIT_EVIDENCE_ONLY = "NAIVE_INVERSE_AUDIT_EVIDENCE_ONLY"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_MAX_CANDIDATES = 20
PRIMARY_MIN_TRUE_PAPER_SAMPLES = 30
WATCHLIST_MIN_TRUE_PAPER_SAMPLES = 30

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R96 is betrayal true-paper scaffold only. No orders, no payloads, no env changes, no network, no Binance."


def build_betrayal_true_paper_scaffold(
    *,
    symbol: str = DEFAULT_SYMBOL,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    dry_run: bool = True,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC).isoformat()
    audit = build_betrayal_strategy_audit(log_dir=resolved_log_dir)
    ledger_path = betrayal_true_paper_outcomes_path(resolved_log_dir)
    outcome_counts = _outcome_counts(ledger_path)
    candidates = _scaffold_candidates(audit=audit, symbol=symbol, outcome_counts=outcome_counts)
    top = candidates[: max(0, int(max_candidates))]
    aggregate_decomposition = [
        row for row in top if row.get("audit_scope") == "timeframe_aggregate" and not row.get("betrayal_direction")
    ]
    rejected_or_deferred = _rejected_or_deferred(audit=audit, symbol=symbol)
    statuses = _r96_statuses(top)
    summary = {
        "scaffold_candidate_count": len(candidates),
        "top_scaffold_candidate_count": len(top),
        "aggregate_decomposition_required_count": len(aggregate_decomposition),
        "true_paper_outcomes_count": sum(int(row.get("true_paper_outcomes_count") or 0) for row in top),
        "live_ready_count": 0,
        "audit_evidence_only": True,
    }
    payload = _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at,
            "symbol": symbol,
            "r96_statuses": statuses,
            "scaffold_summary": summary,
            "scaffold_candidates": candidates,
            "top_scaffold_candidates": top,
            "aggregate_candidates_needing_decomposition": aggregate_decomposition,
            "rejected_or_deferred_candidates": rejected_or_deferred,
            "outcome_ledger": {
                "outcome_ledger_path": str(ledger_path),
                "outcome_ledger_exists": ledger_path.exists(),
                "outcome_schema": _outcome_schema(),
                "fake_outcomes_created": False,
            },
            "outcome_ledger_path": str(ledger_path),
            "minimum_sample_requirements": _minimum_sample_requirements(),
            "next_action_recommendation": "R97 Betrayal Paper Outcome Ledger + First Tracking Loop",
            "blockers": _blockers(top),
            "dry_run": bool(dry_run),
            "write": bool(write),
            "report_written": False,
            "report_path": str(betrayal_true_paper_scaffold_path(resolved_log_dir)),
            "notes": [
                NO_ORDER_NOTE,
                "Betrayal audit candidates are not true paper evidence until real inverse outcomes are recorded.",
                "R96 declares identities and schema only; it does not create risk contracts.",
            ],
            "review_only": True,
            "executable": False,
            "env_modified": False,
            "order_type": "not_created",
            **_safety_fields(),
        }
    )
    if write and not dry_run:
        write_betrayal_true_paper_scaffold(payload, log_dir=resolved_log_dir)
        payload["report_written"] = True
    return _sanitize(payload)


def betrayal_true_paper_scaffold_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / REPORT_FILENAME


def betrayal_true_paper_outcomes_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / OUTCOMES_FILENAME


def write_betrayal_true_paper_scaffold(report: Mapping[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = betrayal_true_paper_scaffold_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_sanitize(dict(report)), handle, sort_keys=True, indent=2)
        handle.write("\n")


def format_betrayal_true_paper_scaffold_text(payload: Mapping[str, Any]) -> str:
    summary = payload.get("scaffold_summary") if isinstance(payload.get("scaffold_summary"), dict) else {}
    ledger = payload.get("outcome_ledger") if isinstance(payload.get("outcome_ledger"), dict) else {}
    requirements = payload.get("minimum_sample_requirements") if isinstance(payload.get("minimum_sample_requirements"), dict) else {}
    top = payload.get("top_scaffold_candidates") if isinstance(payload.get("top_scaffold_candidates"), list) else []
    lines = [
        f"R96 Betrayal True Paper Scaffold status: {payload.get('status')}",
        str(payload.get("execution_mode")),
        f"scaffold_candidates: {summary.get('top_scaffold_candidate_count')}",
        f"ledger_path: {ledger.get('outcome_ledger_path')}",
        f"primary_min_samples: {requirements.get('primary_min_true_paper_samples')}",
        f"watchlist_min_samples: {requirements.get('watchlist_min_true_paper_samples')}",
        "top_betrayal_paper_identities:",
    ]
    if not top:
        lines.append("  none")
    for row in top[:8]:
        lines.append(
            "  "
            f"{row.get('betrayal_paper_signal_id')} hash={row.get('betrayal_paper_signal_hash')} "
            f"evidence={row.get('evidence_label')} true_paper_required={row.get('true_paper_required')} "
            f"outcomes={row.get('true_paper_outcomes_count')} maturity={row.get('maturity_status')}"
        )
    lines.extend(
        [
            f"next_action_recommendation: {payload.get('next_action_recommendation')}",
            f"report_written: {payload.get('report_written')} report_path: {payload.get('report_path')}",
            f"executable: {payload.get('executable')} review_only: {payload.get('review_only')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            "No-order/no-network/no-env-change safety note: R96 is true-paper scaffold only.",
            NO_ORDER_NOTE,
        ]
    )
    return "\n".join(lines)


def _scaffold_candidates(*, audit: Mapping[str, Any], symbol: str, outcome_counts: Mapping[str, int]) -> list[dict[str, Any]]:
    rows = [
        *_list_field(audit, "timeframe_aggregate_primary_candidates"),
        *_list_field(audit, "direction_entry_mode_primary_candidates"),
        *_list_field(audit, "timeframe_aggregate_watchlist_candidates"),
        *_list_field(audit, "direction_entry_mode_watchlist_candidates"),
    ]
    candidates = [_scaffold_candidate(row, symbol=symbol, outcome_counts=outcome_counts) for row in rows if isinstance(row, dict)]
    candidates.sort(key=_sort_key)
    return candidates


def _scaffold_candidate(row: Mapping[str, Any], *, symbol: str, outcome_counts: Mapping[str, int]) -> dict[str, Any]:
    original = row.get("original") if isinstance(row.get("original"), dict) else {}
    betrayal = row.get("betrayal") if isinstance(row.get("betrayal"), dict) else {}
    identity = _identity_fields(row=row, symbol=symbol)
    signal_id = _paper_signal_id(identity)
    signal_hash = _paper_signal_hash(identity)
    outcomes = int(outcome_counts.get(signal_hash) or outcome_counts.get(signal_id) or 0)
    classification = str(row.get("recommendation") or "")
    min_samples = PRIMARY_MIN_TRUE_PAPER_SAMPLES if classification == BETRAYAL_PRIMARY_CANDIDATE else WATCHLIST_MIN_TRUE_PAPER_SAMPLES
    aggregate_needs_decomposition = identity["audit_scope"] == "timeframe_aggregate" and identity["direction_part"] == "aggregate"
    maturity = PAPER_IDENTITY_CREATED if aggregate_needs_decomposition else PAPER_TRACKING_READY
    if outcomes > 0 and outcomes < min_samples:
        maturity = PAPER_EVIDENCE_INSUFFICIENT
    elif outcomes >= min_samples and not aggregate_needs_decomposition:
        maturity = PAPER_READY_FOR_REVIEW
    return {
        "betrayal_paper_signal_id": signal_id,
        "betrayal_paper_signal_hash": signal_hash,
        "candidate_classification": classification,
        "audit_scope": identity["audit_scope"],
        "symbol": identity["symbol"],
        "timeframe": identity["timeframe"],
        "original_direction": identity.get("original_direction"),
        "betrayal_direction": identity.get("betrayal_direction"),
        "entry_mode": identity.get("entry_mode"),
        "sample_count": row.get("sample_count"),
        "original_win_rate_pct": original.get("win_rate_pct"),
        "naive_inverse_win_rate_pct": betrayal.get("win_rate_pct"),
        "original_total_pnl_pct": original.get("total_pnl_pct"),
        "naive_inverse_total_pnl_pct": betrayal.get("total_pnl_pct"),
        "original_avg_pnl_pct": original.get("avg_pnl_pct"),
        "naive_inverse_avg_pnl_pct": betrayal.get("avg_pnl_pct"),
        "audit_score": _audit_score(row),
        "evidence_label": NAIVE_INVERSE_AUDIT_EVIDENCE_ONLY,
        "true_paper_required": True,
        "true_paper_outcomes_count": outcomes,
        "true_paper_min_samples_required": min_samples,
        "aggregate_requires_directional_decomposition": aggregate_needs_decomposition,
        "stop_take_profit_required_before_promotion": True,
        "miro_fish_markov_equivalent_required": True,
        "maturity_status": maturity,
        "maturity_statuses": list(dict.fromkeys([AUDIT_ONLY, maturity, PAPER_OUTCOMES_PENDING, LIVE_READY_FALSE])),
        "live_ready": False,
        "executable": False,
        "required_next_steps": _required_next_steps(aggregate_needs_decomposition=aggregate_needs_decomposition),
    }


def _identity_fields(*, row: Mapping[str, Any], symbol: str) -> dict[str, Any]:
    audit_scope = str(row.get("audit_scope") or "timeframe_aggregate")
    timeframe = str(row.get("timeframe") or "unknown")
    original_direction = row.get("original_direction")
    betrayal_direction = row.get("betrayal_direction")
    entry_mode = row.get("entry_mode")
    if audit_scope == "timeframe_aggregate" and not (original_direction or betrayal_direction or entry_mode):
        direction_part = "aggregate"
        entry_part = None
    else:
        direction_part = f"{original_direction}_to_{betrayal_direction}"
        entry_part = str(entry_mode or "unknown_entry")
    return {
        "symbol": symbol or DEFAULT_SYMBOL,
        "timeframe": timeframe,
        "audit_scope": audit_scope,
        "candidate_classification": row.get("recommendation"),
        "original_direction": original_direction,
        "betrayal_direction": betrayal_direction,
        "entry_mode": entry_mode,
        "direction_part": direction_part,
        "entry_part": entry_part,
    }


def _paper_signal_id(identity: Mapping[str, Any]) -> str:
    if identity.get("direction_part") == "aggregate":
        return f"betrayal|{identity.get('symbol')}|{identity.get('timeframe')}|aggregate|{identity.get('audit_scope')}"
    return (
        f"betrayal|{identity.get('symbol')}|{identity.get('timeframe')}|"
        f"{identity.get('direction_part')}|{identity.get('entry_part')}|{identity.get('audit_scope')}"
    )


def _paper_signal_hash(identity: Mapping[str, Any]) -> str:
    stable = {
        "audit_scope": identity.get("audit_scope"),
        "betrayal_direction": identity.get("betrayal_direction"),
        "candidate_classification": identity.get("candidate_classification"),
        "entry_mode": identity.get("entry_mode"),
        "original_direction": identity.get("original_direction"),
        "symbol": identity.get("symbol"),
        "timeframe": identity.get("timeframe"),
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _outcome_counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not path.exists():
        return counts
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            for key in (record.get("candidate_hash"), record.get("betrayal_paper_signal_id")):
                if key:
                    counts[str(key)] = counts.get(str(key), 0) + 1
    return counts


def _rejected_or_deferred(*, audit: Mapping[str, Any], symbol: str) -> list[dict[str, Any]]:
    rows = [*_list_field(audit, "timeframe_aggregate_rejected_candidates"), *_list_field(audit, "direction_entry_mode_rejected_candidates")]
    deferred = []
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        identity = _identity_fields(row=row, symbol=symbol)
        deferred.append(
            {
                "betrayal_paper_signal_id": _paper_signal_id(identity),
                "candidate_classification": row.get("recommendation"),
                "audit_scope": row.get("audit_scope"),
                "timeframe": row.get("timeframe"),
                "deferred_reason": row.get("blockers") or ["not currently a betrayal paper scaffold candidate"],
                "live_ready": False,
            }
        )
    return deferred


def _minimum_sample_requirements() -> dict[str, Any]:
    return {
        "primary_min_true_paper_samples": PRIMARY_MIN_TRUE_PAPER_SAMPLES,
        "watchlist_min_true_paper_samples": WATCHLIST_MIN_TRUE_PAPER_SAMPLES,
        "aggregate_requires_directional_decomposition": True,
        "stop_take_profit_required_before_promotion": True,
        "miro_fish_markov_equivalent_required_before_risk_contract": True,
    }


def _outcome_schema() -> dict[str, Any]:
    return {
        "outcome_id": "string",
        "betrayal_paper_signal_id": "string",
        "candidate_hash": "string",
        "symbol": "string",
        "timeframe": "string",
        "direction": "string",
        "entry_mode": "string|null",
        "source_signal_id": "string",
        "source_timestamp": "iso8601",
        "paper_entry_price": "number",
        "paper_stop_price": "number",
        "paper_take_profit_price": "number",
        "paper_exit_price": "number",
        "paper_exit_reason": "string",
        "paper_pnl_pct": "number",
        "paper_result_win_loss": "win|loss",
        "max_adverse_excursion_pct": "number|null",
        "max_favorable_excursion_pct": "number|null",
        "created_at": "iso8601",
        "closed_at": "iso8601|null",
        "data_source": "string",
        "review_only": True,
        "live_order_id": None,
        "real_order_placed": False,
        "order_payload_created": False,
    }


def _required_next_steps(*, aggregate_needs_decomposition: bool) -> list[str]:
    steps = []
    if aggregate_needs_decomposition:
        steps.append("decompose aggregate candidate into directional entry-mode paper identity")
    steps.extend(
        [
            "create betrayal paper signal identity",
            "track actual inverse entries/exits",
            "record stop/take-profit behavior",
            "collect minimum samples",
            "evaluate with Miro Fish/Markov equivalent",
            "only then consider risk contract",
        ]
    )
    return steps


def _audit_score(row: Mapping[str, Any]) -> float:
    betrayal = row.get("betrayal") if isinstance(row.get("betrayal"), dict) else {}
    classification_bonus = 100.0 if row.get("recommendation") == BETRAYAL_PRIMARY_CANDIDATE else 50.0
    scope_bonus = 10.0 if row.get("audit_scope") == "direction_entry_mode" else 0.0
    return round(
        classification_bonus
        + scope_bonus
        + float(row.get("sample_count") or 0) / 10.0
        + float(betrayal.get("win_rate_pct") or 0.0)
        + max(0.0, float(betrayal.get("total_pnl_pct") or 0.0)),
        4,
    )


def _sort_key(row: Mapping[str, Any]) -> tuple[int, float, int, float, float, int]:
    classification_rank = 0 if row.get("candidate_classification") == BETRAYAL_PRIMARY_CANDIDATE else 1
    scope_rank = 0 if row.get("audit_scope") == "direction_entry_mode" else 1
    return (
        classification_rank,
        -float(row.get("audit_score") or 0.0),
        scope_rank,
        -float(row.get("sample_count") or 0),
        -float(row.get("naive_inverse_win_rate_pct") or 0),
        -float(row.get("naive_inverse_total_pnl_pct") or 0),
    )


def _r96_statuses(candidates: list[Mapping[str, Any]]) -> list[str]:
    statuses = [BETRAYAL_TRUE_PAPER_SCAFFOLD_ONLY]
    if candidates:
        statuses.extend([BETRAYAL_AUDIT_CANDIDATES_FOUND, BETRAYAL_PAPER_IDENTITIES_CREATED])
    statuses.extend(
        [
            BETRAYAL_OUTCOME_LEDGER_DECLARED,
            BETRAYAL_TRUE_PAPER_OUTCOMES_REQUIRED,
            BETRAYAL_MINIMUM_SAMPLE_REQUIREMENTS_DECLARED,
            BETRAYAL_NOT_LIVE_READY,
            BETRAYAL_NON_EXECUTABLE_ONLY,
        ]
    )
    return list(dict.fromkeys(statuses))


def _blockers(candidates: list[Mapping[str, Any]]) -> list[str]:
    blockers = ["true_paper_outcomes_required", "risk_contract_not_created_in_r96", "r96_scaffold_only_not_live_permission"]
    if not candidates:
        blockers.append("no_current_betrayal_audit_candidates")
    if any(row.get("aggregate_requires_directional_decomposition") for row in candidates):
        blockers.append("aggregate_candidates_require_directional_decomposition")
    return list(dict.fromkeys(blockers))


def _list_field(payload: Mapping[str, Any], key: str) -> list:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _safety_fields() -> dict[str, Any]:
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": ALLOW_LIVE_ORDERS,
        "global_kill_switch": GLOBAL_KILL_SWITCH,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "order_payload_created": ORDER_PAYLOAD_CREATED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in (
            "live_execution_enabled",
            "allow_live_orders",
            "order_placed",
            "real_order_placed",
            "execution_attempted",
            "order_payload_created",
            "network_allowed",
            "secrets_shown",
            "executable",
            "env_modified",
            "live_ready",
            "fake_outcomes_created",
        ):
            if key in sanitized:
                sanitized[key] = False
        if "global_kill_switch" in sanitized:
            sanitized["global_kill_switch"] = True
        if "review_only" in sanitized:
            sanitized["review_only"] = True
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, tuple):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, Path):
        return str(payload)
    return payload
