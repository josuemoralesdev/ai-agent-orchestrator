"""R221 betrayal registry consumer refactor report.

Paper-only compatibility and gap report for betrayal-family consumers that
should consume the R218 strategy evidence registry and R219 wiring output.
It appends only its own R221 ledger after explicit confirmation.
"""

from __future__ import annotations

import importlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.strategy_evidence_registry import validate_registry_entry

BETRAYAL_REGISTRY_CONSUMER_REFACTOR_READY = "BETRAYAL_REGISTRY_CONSUMER_REFACTOR_READY"
BETRAYAL_REGISTRY_CONSUMER_REFACTOR_REJECTED = "BETRAYAL_REGISTRY_CONSUMER_REFACTOR_REJECTED"
BETRAYAL_REGISTRY_CONSUMER_REFACTOR_RECORDED = "BETRAYAL_REGISTRY_CONSUMER_REFACTOR_RECORDED"
BETRAYAL_REGISTRY_CONSUMER_REFACTOR_BLOCKED = "BETRAYAL_REGISTRY_CONSUMER_REFACTOR_BLOCKED"
BETRAYAL_REGISTRY_CONSUMER_REFACTOR_ERROR = "BETRAYAL_REGISTRY_CONSUMER_REFACTOR_ERROR"

BETRAYAL_CONSUMERS_REGISTRY_BACKED = "BETRAYAL_CONSUMERS_REGISTRY_BACKED"
BETRAYAL_CONSUMERS_PARTIALLY_REGISTRY_BACKED = "BETRAYAL_CONSUMERS_PARTIALLY_REGISTRY_BACKED"
BETRAYAL_CONSUMERS_REGISTRY_GAPS_REMAIN = "BETRAYAL_CONSUMERS_REGISTRY_GAPS_REMAIN"
BETRAYAL_CONSUMERS_REGISTRY_MISSING = "BETRAYAL_CONSUMERS_REGISTRY_MISSING"
BETRAYAL_CONSUMERS_NOT_LIVE_AUTHORIZED = "BETRAYAL_CONSUMERS_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_REGISTRY_CONSUMER_REFACTOR"
LEDGER_FILENAME = "betrayal_registry_consumer_refactor.ndjson"
CONFIRM_BETRAYAL_REGISTRY_CONSUMER_REFACTOR_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL REGISTRY CONSUMER REFACTOR RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

TARGET_CONSUMER_MODULES = (
    "betrayal_source_emitter_refresh",
    "betrayal_aggregate_decomposition",
    "betrayal_direction_split_resolver",
    "betrayal_event_tracker",
)
AUDIT_ONLY_MODULES = (
    "betrayal_paper_matrix_context",
    "betrayal_true_inverse_refresh",
    "betrayal_integration_recheck",
)
MODULE_BASE = "src.app.hammer_radar.operator"

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "registry_config_written": False,
    "scoring_config_written": False,
    "matrix_config_written": False,
    "risk_contract_config_written": False,
    "lane_config_written": False,
    "ledger_rewritten": False,
    "destructive_write": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "network_allowed": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
    "live_authorization_created": False,
    "signal_origin_promoted": False,
    "lane_promoted": False,
    "betrayal_live_authorized": False,
    "betrayal_promoted": False,
    "position_permission_created": False,
}


def build_betrayal_registry_consumer_refactor(
    *,
    log_dir: str | Path | None = None,
    record_refactor: bool = False,
    confirm_betrayal_registry_consumer_refactor: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_betrayal_registry_consumer_refactor == CONFIRM_BETRAYAL_REGISTRY_CONSUMER_REFACTOR_RECORDING_PHRASE
    try:
        registry = load_latest_strategy_evidence_registry(log_dir=resolved_log_dir)
        wiring = load_latest_registry_wiring_betrayal_source_family(log_dir=resolved_log_dir)
        manifest = _registry_manifest(registry)
        registry_validation = _registry_validation(registry, manifest)
        inventory = build_betrayal_registry_consumer_inventory(log_dir=resolved_log_dir)
        compatibility = build_registry_consumer_compatibility_report(inventory)
        gap_report = build_registry_consumer_gap_report(
            inventory=inventory,
            registry_found=bool(registry),
            registry_valid=bool(registry_validation.get("valid")),
            wiring=wiring,
        )
        consumer_status = classify_betrayal_registry_consumer_status(
            registry_found=bool(registry),
            registry_valid=bool(registry_validation.get("valid")),
            inventory=inventory,
            gap_report=gap_report,
        )
        payload = {
            "status": _top_level_status(
                record_refactor=record_refactor,
                confirmation_valid=confirmation_valid,
                registry_found=bool(registry),
                registry_valid=bool(registry_validation.get("valid")),
            ),
            "generated_at": generated_at.isoformat(),
            "refactor_recorded": False,
            "refactor_id": None,
            "record_refactor_requested": bool(record_refactor),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "family": "betrayal",
                "registry_backed": bool(registry),
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "strategy_evidence_registry_found": bool(registry),
                "registry_valid": bool(registry_validation.get("valid")),
                "registry_wiring_found": bool(wiring),
                "target_modules_inspected": list(TARGET_CONSUMER_MODULES),
            },
            "registry_consumer_inventory": _public_inventory(inventory),
            "registry_consumer_compatibility_report": compatibility,
            "registry_consumer_gap_report": gap_report,
            "registry_consumer_recommendations": build_registry_consumer_recommendations(gap_report=gap_report),
            "consumer_status": consumer_status,
            "recommended_next_operator_move": _recommended_next_operator_move(consumer_status, gap_report),
            "recommended_next_engineering_move": _recommended_next_engineering_move(consumer_status, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
        }
        if record_refactor and confirmation_valid and registry_validation.get("valid"):
            record = append_betrayal_registry_consumer_refactor_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_REGISTRY_CONSUMER_REFACTOR_RECORDED
            payload["refactor_recorded"] = True
            payload["refactor_id"] = record["refactor_id"]
            payload["ledger_path"] = str(betrayal_registry_consumer_refactor_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_REGISTRY_CONSUMER_REFACTOR_ERROR,
                "generated_at": generated_at.isoformat(),
                "refactor_recorded": False,
                "refactor_id": None,
                "record_refactor_requested": bool(record_refactor),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {"family": "betrayal", "registry_backed": False, "paper_only": True, "live_authorized": False},
                "input_summary": {"target_modules_inspected": list(TARGET_CONSUMER_MODULES)},
                "registry_consumer_inventory": [],
                "registry_consumer_compatibility_report": build_registry_consumer_compatibility_report([]),
                "registry_consumer_gap_report": {
                    "remaining_hardcoded_candidate_lists": [],
                    "remaining_hardcoded_required_fields": [],
                    "remaining_hardcoded_safety_defaults": [],
                    "entry_mode_source_identity_still_blocked": True,
                    "resolver_ready_rows": 0,
                    "hard_live_blockers": _hard_live_blockers(),
                },
                "registry_consumer_recommendations": [],
                "consumer_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_WEEKEND_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R221 consumer refactor report error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
            }
        )


def load_latest_strategy_evidence_registry(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "strategy_evidence_registry.ndjson")


def load_latest_registry_wiring_betrayal_source_family(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "registry_wiring_betrayal_source_family.ndjson")


def build_betrayal_registry_consumer_inventory(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    del log_dir
    rows = []
    for module_name in (*TARGET_CONSUMER_MODULES, *AUDIT_ONLY_MODULES):
        rows.append(inspect_betrayal_module_registry_usage(module_name))
    return rows


def inspect_betrayal_module_registry_usage(module_name: str) -> dict[str, Any]:
    module = importlib.import_module(f"{MODULE_BASE}.{module_name}")
    path = Path(module.__file__ or "")
    source = path.read_text(encoding="utf-8") if path.exists() else ""
    target = module_name in TARGET_CONSUMER_MODULES
    consumes_candidates = "get_betrayal_candidates_from_registry" in source or "build_registry_backed_betrayal_candidate_view" in source
    consumes_requirements = "get_betrayal_source_required_fields_from_registry" in source or "required_source_fields" in source
    consumes_safety = "get_betrayal_safety_defaults_from_registry" in source or "safety_defaults" in source
    hardcoded = _hardcoded_list_hits(source, path=path)
    fallback = "legacy_context_only" if "fallback_behavior_if_registry_missing" in source else "unknown"
    if target and not source:
        fallback = "blocked"
    notes = []
    if target and consumes_candidates:
        notes.append("target consumer imports R219 registry-backed candidate view")
    if target and consumes_requirements:
        notes.append("target consumer exposes registry-backed source requirements")
    if target and consumes_safety:
        notes.append("target consumer exposes registry-backed safety defaults")
    if hardcoded:
        notes.append("hardcoded target list references remain for fallback or legacy context")
    if not target:
        notes.append("audit-only module; no heavy refactor applied in R221")
    return _sanitize(
        {
            "module": module_name,
            "path": str(path),
            "consumes_betrayal_candidates_from_registry": bool(consumes_candidates),
            "consumes_source_identity_requirements_from_registry": bool(consumes_requirements),
            "consumes_safety_defaults_from_registry": bool(consumes_safety),
            "hardcoded_target_list_remaining": bool(hardcoded),
            "fallback_behavior_if_registry_missing": fallback,
            "paper_only": True,
            "live_authorized": False,
            "notes": notes,
            "_hardcoded_hits": hardcoded,
        }
    )


def build_registry_consumer_compatibility_report(inventory: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    target_rows = [row for row in inventory if row.get("module") in TARGET_CONSUMER_MODULES]
    registry_backed = [
        row
        for row in target_rows
        if row.get("consumes_betrayal_candidates_from_registry")
        and row.get("consumes_source_identity_requirements_from_registry")
        and row.get("consumes_safety_defaults_from_registry")
    ]
    partial = [row for row in target_rows if row not in registry_backed and _any_registry_flag(row)]
    return {
        "modules_inspected": len(inventory),
        "modules_registry_backed": len(registry_backed),
        "modules_partially_registry_backed": len(partial),
        "modules_with_hardcoded_lists_remaining": sum(1 for row in inventory if row.get("hardcoded_target_list_remaining")),
        "modules_with_safe_fallback": sum(1 for row in inventory if row.get("fallback_behavior_if_registry_missing") in {"blocked", "legacy_context_only"}),
        "registry_missing_would_block_readiness": True,
    }


def build_registry_consumer_gap_report(
    *,
    inventory: Sequence[Mapping[str, Any]],
    registry_found: bool,
    registry_valid: bool,
    wiring: Mapping[str, Any],
) -> dict[str, Any]:
    missing_report = wiring.get("registry_backed_missing_field_report") if isinstance(wiring.get("registry_backed_missing_field_report"), Mapping) else {}
    wiring_gap = wiring.get("registry_wiring_gap_report") if isinstance(wiring.get("registry_wiring_gap_report"), Mapping) else {}
    return {
        "remaining_hardcoded_candidate_lists": _hits_by_kind(inventory, "candidate"),
        "remaining_hardcoded_required_fields": _hits_by_kind(inventory, "required_fields"),
        "remaining_hardcoded_safety_defaults": _hits_by_kind(inventory, "safety"),
        "entry_mode_source_identity_still_blocked": bool(
            missing_report.get("missing_entry_mode_rows")
            or missing_report.get("missing_source_identity_rows")
            or wiring_gap.get("entry_mode_blocked")
            or wiring_gap.get("betrayal_source_identity_blocked")
        ),
        "resolver_ready_rows": int(missing_report.get("resolver_ready_rows") or wiring_gap.get("resolver_ready_rows") or 0),
        "registry_missing": not registry_found,
        "registry_valid": bool(registry_valid),
        "hard_live_blockers": _hard_live_blockers(),
    }


def build_registry_consumer_recommendations(*, gap_report: Mapping[str, Any]) -> list[dict[str, str]]:
    recommendations = []
    if gap_report.get("registry_missing") or not gap_report.get("registry_valid"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "RECORD_R218_REGISTRY",
                "future_phase": "R218",
                "why": "Consumer refactor reporting cannot become registry-backed without a valid strategy evidence registry.",
            }
        )
    if gap_report.get("remaining_hardcoded_candidate_lists"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "WIRE_MODULE_TO_REGISTRY",
                "future_phase": "R222",
                "why": "Some modules still carry literal candidate/timeframe lists for legacy fallback or audit-only context.",
            }
        )
    if gap_report.get("entry_mode_source_identity_still_blocked"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "RUN_R223_SOURCE_IDENTITY_NORMALIZER",
                "future_phase": "R223",
                "why": "R219 still reports entry_mode/source_identity gaps; R221 only wires consumers and must not synthesize evidence.",
            }
        )
    recommendations.append(
        {
            "priority": "LOW",
            "recommended_action": "KEEP_CONTEXT_ONLY",
            "future_phase": "R221",
            "why": "Registry consumption is paper-only and does not promote betrayal, lane modes, or live authorization.",
        }
    )
    return recommendations


def classify_betrayal_registry_consumer_status(
    *,
    registry_found: bool,
    registry_valid: bool,
    inventory: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
) -> str:
    if not registry_found or not registry_valid:
        return BETRAYAL_CONSUMERS_REGISTRY_MISSING
    target_rows = [row for row in inventory if row.get("module") in TARGET_CONSUMER_MODULES]
    if not target_rows:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    fully_backed = [
        row
        for row in target_rows
        if row.get("consumes_betrayal_candidates_from_registry")
        and row.get("consumes_source_identity_requirements_from_registry")
        and row.get("consumes_safety_defaults_from_registry")
    ]
    if len(fully_backed) == len(target_rows) and not gap_report.get("remaining_hardcoded_candidate_lists"):
        return BETRAYAL_CONSUMERS_REGISTRY_BACKED
    if fully_backed:
        return BETRAYAL_CONSUMERS_PARTIALLY_REGISTRY_BACKED
    if any(_any_registry_flag(row) for row in target_rows):
        return BETRAYAL_CONSUMERS_REGISTRY_GAPS_REMAIN
    return BETRAYAL_CONSUMERS_NOT_LIVE_AUTHORIZED


def append_betrayal_registry_consumer_refactor_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_registry_consumer_refactor_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "refactor_id": str(record.get("refactor_id") or f"r221_betrayal_registry_consumer_refactor_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_REGISTRY_CONSUMER_REFACTOR_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_refactor_requested": bool(record.get("record_refactor_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "registry_consumer_inventory": _public_inventory(list(record.get("registry_consumer_inventory") or [])),
            "registry_consumer_compatibility_report": dict(record.get("registry_consumer_compatibility_report") or {}),
            "registry_consumer_gap_report": dict(record.get("registry_consumer_gap_report") or {}),
            "registry_consumer_recommendations": list(record.get("registry_consumer_recommendations") or []),
            "consumer_status": record.get("consumer_status"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": dict(SAFETY),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_betrayal_registry_consumer_refactor_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_registry_consumer_refactor_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_betrayal_registry_consumer_refactor_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "consumer_status_counts": dict(sorted(Counter(str(record.get("consumer_status") or "UNKNOWN") for record in records).items())),
        "last_refactor_id": latest.get("refactor_id") if isinstance(latest, Mapping) else None,
        "last_consumer_status": latest.get("consumer_status") if isinstance(latest, Mapping) else None,
        "safety": dict(SAFETY),
    }


def betrayal_registry_consumer_refactor_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_registry_consumer_refactor_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _top_level_status(*, record_refactor: bool, confirmation_valid: bool, registry_found: bool, registry_valid: bool) -> str:
    if record_refactor and not confirmation_valid:
        return BETRAYAL_REGISTRY_CONSUMER_REFACTOR_REJECTED
    if not registry_found or not registry_valid:
        return BETRAYAL_REGISTRY_CONSUMER_REFACTOR_BLOCKED
    if record_refactor and confirmation_valid:
        return BETRAYAL_REGISTRY_CONSUMER_REFACTOR_RECORDED
    return BETRAYAL_REGISTRY_CONSUMER_REFACTOR_READY


def _registry_manifest(registry: Mapping[str, Any]) -> dict[str, Any]:
    manifest = registry.get("registry_manifest") if isinstance(registry.get("registry_manifest"), Mapping) else registry
    return dict(manifest) if isinstance(manifest, Mapping) else {}


def _registry_validation(registry: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    if not registry or not manifest:
        return {"valid": False, "missing_required_sections": ["registry_manifest"]}
    if isinstance(registry.get("registry_validation"), Mapping):
        return dict(registry["registry_validation"])
    return validate_registry_entry(manifest)


def _latest_record(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    records = read_recent_ndjson_records(path, limit=1, max_bytes=16_777_216)
    return _sanitize(records[0]) if records else {}


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                rows.append(_sanitize(dict(value)))
    return rows


def _hardcoded_list_hits(source: str, *, path: Path) -> list[dict[str, Any]]:
    hits = []
    patterns = {
        "candidate": r"(TARGET_TIMEFRAMES|TARGET_CANDIDATES|222m aggregate|88m aggregate|55m aggregate)",
        "required_fields": r"(REQUIRED_FIELDS\s*=|schema_version|source_identity|betrayal_event_identity_hash)",
        "safety": r"(SAFETY\s*=|paper_only|live_authorized|promotion_allowed)",
    }
    for index, line in enumerate(source.splitlines(), start=1):
        for kind, pattern in patterns.items():
            if re.search(pattern, line):
                hits.append({"kind": kind, "path": str(path), "line": index, "text": line.strip()[:180]})
    return hits


def _hits_by_kind(inventory: Sequence[Mapping[str, Any]], kind: str) -> list[dict[str, Any]]:
    rows = []
    for item in inventory:
        module = str(item.get("module") or "unknown")
        for hit in item.get("_hardcoded_hits") or []:
            if isinstance(hit, Mapping) and hit.get("kind") == kind:
                rows.append({"module": module, **dict(hit)})
    return rows


def _public_inventory(inventory: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {str(key): value for key, value in row.items() if str(key) != "_hardcoded_hits"}
        for row in inventory
        if isinstance(row, Mapping)
    ]


def _any_registry_flag(row: Mapping[str, Any]) -> bool:
    return bool(
        row.get("consumes_betrayal_candidates_from_registry")
        or row.get("consumes_source_identity_requirements_from_registry")
        or row.get("consumes_safety_defaults_from_registry")
    )


def _recommended_next_operator_move(consumer_status: str, gap_report: Mapping[str, Any]) -> str:
    if gap_report.get("entry_mode_source_identity_still_blocked"):
        return "RUN_R223_BETRAYAL_SOURCE_IDENTITY_NORMALIZER"
    if consumer_status == BETRAYAL_CONSUMERS_REGISTRY_MISSING:
        return "RUN_R220_REGISTRY_WIRING_FOR_PATTERN_ANCHOR_FAMILIES"
    return "KEEP_WEEKEND_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(consumer_status: str, gap_report: Mapping[str, Any]) -> str:
    if gap_report.get("entry_mode_source_identity_still_blocked"):
        return "Use registry-backed requirements in R223 to normalize source_identity/entry_mode only where local evidence supports it."
    if gap_report.get("remaining_hardcoded_candidate_lists"):
        return "Continue removing duplicate target lists where behavior can remain backward compatible; keep audit-only modules context-only."
    if consumer_status == BETRAYAL_CONSUMERS_REGISTRY_MISSING:
        return "Repair or record R218/R219 registry artifacts before treating consumer inventory as registry-backed."
    return "Keep betrayal paper-only; registry consumer wiring is not promotion or live readiness."


def _hard_live_blockers() -> list[str]:
    return [
        "registry_inclusion_is_not_live_authorization",
        "betrayal_not_live_authorized",
        "betrayal_not_promoted",
        "config_writes_forbidden",
        "orders_forbidden",
        "binance_calls_forbidden",
        "live_authorization_forbidden",
    ]


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set any lane tiny_live",
        "write risk contract config",
        "transfer",
        "withdraw",
    ]


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, set):
        return sorted(_sanitize(item) for item in value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
