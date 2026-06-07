"""R218 strategy evidence registry / source identity manifest.

Paper-only manifest surface for strategy evidence requirements. It centralizes
timeframes, entry modes, source origins, betrayal candidates, direction rules,
source identity requirements, evidence requirements, and family safety defaults.
It never calls Binance/network, mutates env/config, creates payloads, promotes
origins/lanes, or authorizes live execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.signal_origin_registry import build_signal_origin_registry

STRATEGY_EVIDENCE_REGISTRY_READY = "STRATEGY_EVIDENCE_REGISTRY_READY"
STRATEGY_EVIDENCE_REGISTRY_REJECTED = "STRATEGY_EVIDENCE_REGISTRY_REJECTED"
STRATEGY_EVIDENCE_REGISTRY_RECORDED = "STRATEGY_EVIDENCE_REGISTRY_RECORDED"
STRATEGY_EVIDENCE_REGISTRY_BLOCKED = "STRATEGY_EVIDENCE_REGISTRY_BLOCKED"
STRATEGY_EVIDENCE_REGISTRY_ERROR = "STRATEGY_EVIDENCE_REGISTRY_ERROR"

REGISTRY_MANIFEST_READY = "REGISTRY_MANIFEST_READY"
REGISTRY_MANIFEST_RECORDED = "REGISTRY_MANIFEST_RECORDED"
REGISTRY_GAPS_REMAIN = "REGISTRY_GAPS_REMAIN"
REGISTRY_NOT_LIVE_AUTHORIZED = "REGISTRY_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "STRATEGY_EVIDENCE_REGISTRY"
LEDGER_FILENAME = "strategy_evidence_registry.ndjson"
CONFIRM_STRATEGY_EVIDENCE_REGISTRY_RECORDING_PHRASE = (
    "I CONFIRM STRATEGY EVIDENCE REGISTRY RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

TIMEFRAMES = ("4m", "8m", "13m", "22m", "44m", "55m", "88m", "222m", "444m", "666m", "888m", "4H", "13H", "13D")
ENTRY_MODES = (
    "ladder_close_50_618",
    "ladder_382_50_618",
    "ladder_22_44_22",
    "market_close",
    "fib_618",
    "fib_650",
    "unknown",
    "entry_unknown",
)
NORMAL_SIGNAL_ORIGINS = (
    "hammer_wick_reversal",
    "three_black_crows",
    "bearish_engulfing",
    "bullish_engulfing",
    "three_white_soldiers",
    "exhaustion_wick",
)
CONTEXT_SIGNAL_ORIGINS = (
    "golden_pocket_rejection",
    "rsi_divergence_bearish",
    "rsi_divergence_bullish",
    "wma_ma_anchor_context",
    "breakdown_retest",
    "breakout_retest",
)
ANCHOR_TYPES = ("SMA200", "WMA200", "custom_wma")
ANCHOR_PERIODS = (13, 21, 34, 55, 89, 144, 200, 233, 377, 610, 888)
FAMILIES = ("normal_pattern", "anchor_context", "betrayal", "full_spectrum_harvester")

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

SOURCE_SURFACES_USED = [
    "operator.signal_origin_registry.build_signal_origin_registry",
    "operator.full_spectrum_harvester_expansion.DEFAULT_EXPANDED_TIMEFRAMES",
    "operator.wma_ma_anchor_layer_preview.ANCHOR_TYPES",
    "operator.wma_ma_anchor_layer_preview.DEFAULT_ANCHOR_PERIODS",
    "operator.betrayal_source_emitter_refresh.REQUIRED_FIELDS",
    "operator.betrayal_aggregate_decomposition decomposition requirements",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_strategy_evidence_registry(
    *,
    log_dir: str | Path | None = None,
    record_registry: bool = False,
    confirm_strategy_evidence_registry: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_strategy_evidence_registry == CONFIRM_STRATEGY_EVIDENCE_REGISTRY_RECORDING_PHRASE
    try:
        manifest = {
            "timeframes": get_timeframe_manifest(),
            "entry_modes": get_entry_mode_manifest(),
            "signal_origins": get_signal_origin_manifest(),
            "betrayal_candidates": get_betrayal_candidate_manifest(),
            "anchors": get_anchor_manifest(),
            "direction_rules": get_direction_rule_manifest(),
            "source_identity_requirements": get_source_identity_requirements(),
            "evidence_requirements_by_family": get_evidence_requirements_by_family(),
            "safety_manifest": get_safety_manifest(),
        }
        validation = validate_registry_entry(manifest)
        gap_report = build_registry_gap_report(manifest)
        registry_status = classify_strategy_evidence_registry_status(
            validation=validation,
            record_registry=record_registry,
            confirmation_valid=confirmation_valid,
        )
        payload = {
            "status": _top_level_status(
                record_registry=record_registry,
                confirmation_valid=confirmation_valid,
                validation=validation,
            ),
            "generated_at": generated_at.isoformat(),
            "registry_recorded": False,
            "registry_id": None,
            "record_registry_requested": bool(record_registry),
            "confirmation_valid": bool(confirmation_valid),
            "registry_manifest": manifest,
            "registry_validation": validation,
            "registry_gap_report": gap_report,
            "registry_recommendations": build_registry_recommendations(gap_report=gap_report),
            "registry_status": registry_status,
            "recommended_next_operator_move": _recommended_next_operator_move(gap_report),
            "recommended_next_engineering_move": _recommended_next_engineering_move(gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_registry and confirmation_valid and validation["valid"]:
            record = append_strategy_evidence_registry_record(payload, log_dir=resolved_log_dir)
            payload["status"] = STRATEGY_EVIDENCE_REGISTRY_RECORDED
            payload["registry_recorded"] = True
            payload["registry_id"] = record["registry_id"]
            payload["registry_status"] = REGISTRY_MANIFEST_RECORDED
            payload["ledger_path"] = str(strategy_evidence_registry_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": STRATEGY_EVIDENCE_REGISTRY_ERROR,
                "generated_at": generated_at.isoformat(),
                "registry_recorded": False,
                "registry_id": None,
                "record_registry_requested": bool(record_registry),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "registry_manifest": {},
                "registry_validation": {
                    "valid": False,
                    "missing_required_sections": ["registry_manifest"],
                    "families_with_live_authorized_true": [],
                    "families_with_config_write_allowed_true": [],
                    "families_with_order_allowed_true": [],
                },
                "registry_gap_report": build_registry_gap_report({}),
                "registry_recommendations": [],
                "registry_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_WEEKEND_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R218 registry builder error; keep all families paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def get_timeframe_manifest() -> list[str]:
    return list(TIMEFRAMES)


def get_entry_mode_manifest() -> list[dict[str, Any]]:
    blocked = {"unknown", "entry_unknown"}
    return [
        {
            "entry_mode": entry_mode,
            "blocked_placeholder": entry_mode in blocked,
            "paper_only": True,
            "live_authorized": False,
            "promotion_allowed": False,
        }
        for entry_mode in ENTRY_MODES
    ]


def get_signal_origin_manifest() -> dict[str, Any]:
    registry_by_origin = {str(row.get("signal_origin")): dict(row) for row in build_signal_origin_registry()}
    origins: dict[str, dict[str, Any]] = {}
    for origin in (*NORMAL_SIGNAL_ORIGINS, *CONTEXT_SIGNAL_ORIGINS):
        local = registry_by_origin.get(origin, {})
        origins[origin] = {
            "signal_origin": origin,
            "family": "normal_pattern" if origin in NORMAL_SIGNAL_ORIGINS else "context",
            "availability": local.get("availability") or ("REGISTRY_ONLY" if "retest" in origin else "MANIFEST_ONLY"),
            "direction_support": list(local.get("direction_support") or ["long", "short"]),
            "registry_only": origin in {"breakdown_retest", "breakout_retest", "wma_ma_anchor_context"},
            "paper_only": True,
            "live_authorized": False,
            "promotion_allowed": False,
        }
    return {
        "primary_normal": list(NORMAL_SIGNAL_ORIGINS),
        "secondary_context": list(CONTEXT_SIGNAL_ORIGINS),
        "origins": origins,
    }


def get_betrayal_candidate_manifest() -> dict[str, Any]:
    required = [
        "direction_split",
        "entry_mode",
        "source_identity",
        "true_inverse_samples",
        "regime_support",
        "Miro Fish support",
        "risk contract",
        "operator approval",
        "live gates",
    ]
    candidates = [
        ("222m_aggregate", "222m", "222m aggregate", 39.7, 60.3),
        ("88m_aggregate", "88m", "88m aggregate", 41.2, 58.8),
        ("55m_aggregate_if_available", "55m", "55m aggregate_if_available", None, None),
    ]
    return {
        candidate_id: {
            "candidate_id": candidate_id,
            "timeframe": timeframe,
            "candidate_type": "aggregate",
            "label": label,
            "original_win_rate_pct": original_win_rate_pct,
            "naive_inverse_win_rate_pct": naive_inverse_win_rate_pct,
            "true_inverse_validation_required": True,
            "paper_only": True,
            "live_authorized": False,
            "promotion_allowed": False,
            "required_before_promotion": list(required),
        }
        for candidate_id, timeframe, label, original_win_rate_pct, naive_inverse_win_rate_pct in candidates
    }


def get_anchor_manifest() -> dict[str, Any]:
    return {
        "anchor_types": list(ANCHOR_TYPES),
        "anchor_periods": list(ANCHOR_PERIODS),
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
        "position_permission_created": False,
    }


def get_direction_rule_manifest() -> dict[str, Any]:
    return {
        "normal_pattern": {
            "direction_required": True,
            "allowed_directions": ["long", "short"],
            "direction_source": "detector_or_explicit_signal_row",
            "aggregate_direction_allowed": False,
        },
        "anchor_context": {
            "direction_required": False,
            "allowed_directions": ["long", "short", "neutral", "unknown"],
            "direction_source": "direction_bias_context_only",
            "summary_level_direction_is_weaker": True,
        },
        "betrayal": {
            "direction_required": True,
            "original_direction_required": True,
            "inverse_direction_required": True,
            "emitted_direction_required": True,
            "lane_direction_alone_is_not_enough": True,
            "aggregate_direction_allowed": False,
        },
        "full_spectrum_harvester": {
            "direction_required": True,
            "allowed_directions": ["long", "short"],
            "entry_mode_required": True,
        },
    }


def get_source_identity_requirements() -> dict[str, list[str]]:
    return {
        "normal_signal_origin": [
            "symbol",
            "timeframe",
            "direction",
            "entry_mode",
            "signal_origin",
            "signal_id",
            "signal_timestamp",
            "lane_key",
            "paper_only",
            "live_authorized",
        ],
        "betrayal_source_emitter_v2": [
            "schema_version",
            "source_type",
            "candidate",
            "symbol",
            "timeframe",
            "entry_mode",
            "original_direction",
            "inverse_direction",
            "emitted_direction",
            "source_identity",
            "source_signal_id",
            "emitted_signal_id",
            "source_signal_timestamp",
            "emitted_at",
            "lane_key",
            "betrayal_event_identity",
            "betrayal_event_identity_hash",
            "outcome_windows",
            "paper_only",
            "live_authorized",
            "promotion_allowed",
        ],
        "anchor_context": [
            "symbol",
            "timeframe",
            "anchor_type",
            "anchor_period",
            "anchor_interaction",
            "direction_bias",
            "event_timestamp_or_summary_level",
            "paper_only",
            "live_authorized",
        ],
    }


def get_evidence_requirements_by_family() -> dict[str, list[str]]:
    return {
        "normal_pattern": [
            "detector evidence",
            "outcome mapping",
            "Keter score",
            "lane matrix score",
            "paper tracking",
            "no live authorization",
        ],
        "anchor_context": [
            "anchor events",
            "outcome windows",
            "event-level confluence if possible",
            "summary-level confluence must be marked weaker",
            "no live authorization",
        ],
        "betrayal": [
            "source identity",
            "direction split",
            "entry mode",
            "true inverse sample",
            "regime support",
            "Miro Fish support",
            "paper matrix context",
            "no live authorization",
        ],
        "full_spectrum_harvester": [
            "lane key",
            "signal id",
            "timestamp",
            "direction",
            "entry mode",
            "heartbeat",
            "paper-only confirmation",
        ],
    }


def get_safety_manifest() -> dict[str, dict[str, bool]]:
    return {
        family: {
            "paper_only": True,
            "live_authorized": False,
            "promotion_allowed": False,
            "config_write_allowed": False,
            "order_allowed": False,
            "binance_network_allowed": False,
        }
        for family in FAMILIES
    }


def validate_registry_entry(registry_manifest: Mapping[str, Any]) -> dict[str, Any]:
    required_sections = [
        "timeframes",
        "entry_modes",
        "signal_origins",
        "betrayal_candidates",
        "anchors",
        "direction_rules",
        "source_identity_requirements",
        "evidence_requirements_by_family",
        "safety_manifest",
    ]
    missing = [section for section in required_sections if section not in registry_manifest]
    safety_manifest = registry_manifest.get("safety_manifest") if isinstance(registry_manifest.get("safety_manifest"), Mapping) else {}
    families_with_live = _families_with_true(safety_manifest, "live_authorized")
    families_with_config = _families_with_true(safety_manifest, "config_write_allowed")
    families_with_order = _families_with_true(safety_manifest, "order_allowed")
    source_requirements_valid = validate_source_identity_requirements(
        registry_manifest.get("source_identity_requirements") if isinstance(registry_manifest, Mapping) else {}
    )
    return {
        "valid": not missing and not families_with_live and not families_with_config and not families_with_order and source_requirements_valid["valid"],
        "missing_required_sections": missing,
        "families_with_live_authorized_true": families_with_live,
        "families_with_config_write_allowed_true": families_with_config,
        "families_with_order_allowed_true": families_with_order,
        "source_identity_requirements_valid": source_requirements_valid["valid"],
        "source_identity_requirements_missing": source_requirements_valid["missing_required_fields_by_family"],
    }


def validate_source_identity_requirements(source_identity_requirements: Mapping[str, Any]) -> dict[str, Any]:
    required = get_source_identity_requirements()
    missing: dict[str, list[str]] = {}
    for family, fields in required.items():
        actual = source_identity_requirements.get(family) if isinstance(source_identity_requirements, Mapping) else None
        actual_set = {str(field) for field in actual or []} if isinstance(actual, Sequence) and not isinstance(actual, str) else set()
        missing_fields = [field for field in fields if field not in actual_set]
        if missing_fields:
            missing[family] = missing_fields
    return {"valid": not missing, "missing_required_fields_by_family": missing}


def build_registry_gap_report(registry_manifest: Mapping[str, Any]) -> dict[str, Any]:
    safety_manifest = registry_manifest.get("safety_manifest") if isinstance(registry_manifest.get("safety_manifest"), Mapping) else {}
    hard_live_blockers = [
        "registry_inclusion_is_not_live_authorization",
        "all_registry_families_default_live_authorized_false",
        "risk_contract_required_before_any_future_live_review",
        "operator_approval_required_before_any_future_live_review",
        "live_gates_required_before_any_future_live_review",
    ]
    if _families_with_true(safety_manifest, "live_authorized"):
        hard_live_blockers.append("unexpected_live_authorized_family_in_manifest")
    return {
        "betrayal_missing_entry_mode_source_identity": True,
        "summary_level_anchor_confluence_still_weaker": True,
        "capture_count_sync_missing": True,
        "hard_live_blockers": hard_live_blockers,
    }


def build_registry_recommendations(gap_report: Mapping[str, Any]) -> list[dict[str, str]]:
    recommendations = [
        {
            "priority": "HIGH",
            "recommended_action": "USE_REGISTRY_IN_R219",
            "future_phase": "R219",
            "why": "Betrayal emitter/decomposition/event surfaces need a shared source-identity contract before resolver-ready rows can be produced consistently.",
        },
        {
            "priority": "HIGH",
            "recommended_action": "KEEP_PAPER_ONLY",
            "future_phase": "R219",
            "why": "Registry inclusion does not authorize live trading, promotion, lane mode changes, or order payload creation.",
        },
        {
            "priority": "MEDIUM",
            "recommended_action": "REFACTOR_PHASE_TARGET_LISTS",
            "future_phase": "R220",
            "why": "Pattern, anchor, and harvester phases should consume one manifest for timeframes, origins, anchors, and evidence requirements.",
        },
    ]
    if gap_report.get("capture_count_sync_missing"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "RUN_R208B_FISHERMAN_WATCHDOG_HARDENING",
                "future_phase": "R208B",
                "why": "Capture-count sync remains a separate readiness blocker and must not be inferred from registry completeness.",
            }
        )
    return recommendations


def classify_strategy_evidence_registry_status(
    *,
    validation: Mapping[str, Any],
    record_registry: bool = False,
    confirmation_valid: bool = False,
) -> str:
    if not validation.get("valid"):
        return REGISTRY_GAPS_REMAIN
    if record_registry and confirmation_valid:
        return REGISTRY_MANIFEST_RECORDED
    return REGISTRY_MANIFEST_READY


def append_strategy_evidence_registry_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = strategy_evidence_registry_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "registry_id": str(record.get("registry_id") or f"r218_strategy_evidence_registry_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": STRATEGY_EVIDENCE_REGISTRY_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_registry_requested": bool(record.get("record_registry_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "registry_manifest": dict(record.get("registry_manifest") or {}),
            "registry_validation": dict(record.get("registry_validation") or {}),
            "registry_gap_report": dict(record.get("registry_gap_report") or {}),
            "registry_recommendations": list(record.get("registry_recommendations") or []),
            "registry_status": REGISTRY_MANIFEST_RECORDED,
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_strategy_evidence_registry_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = strategy_evidence_registry_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_strategy_evidence_registry_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "registry_status_counts": dict(
            sorted(Counter(str(record.get("registry_status") or "UNKNOWN") for record in records).items())
        ),
        "last_registry_id": latest.get("registry_id") if isinstance(latest, Mapping) else None,
        "last_registry_status": latest.get("registry_status") if isinstance(latest, Mapping) else None,
        "safety": dict(SAFETY),
    }


def strategy_evidence_registry_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_strategy_evidence_registry_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _top_level_status(*, record_registry: bool, confirmation_valid: bool, validation: Mapping[str, Any]) -> str:
    if record_registry and not confirmation_valid:
        return STRATEGY_EVIDENCE_REGISTRY_REJECTED
    if not validation.get("valid"):
        return STRATEGY_EVIDENCE_REGISTRY_BLOCKED
    if record_registry and confirmation_valid:
        return STRATEGY_EVIDENCE_REGISTRY_RECORDED
    return STRATEGY_EVIDENCE_REGISTRY_READY


def _recommended_next_operator_move(gap_report: Mapping[str, Any]) -> str:
    if gap_report.get("betrayal_missing_entry_mode_source_identity"):
        return "RUN_R219_REGISTRY_WIRING_FOR_BETRAYAL"
    return "KEEP_WEEKEND_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(gap_report: Mapping[str, Any]) -> str:
    if gap_report.get("betrayal_missing_entry_mode_source_identity"):
        return "Wire R219 betrayal source family to consume R218 source identity and direction manifests; keep it paper-only."
    return "Use R218 as the central manifest before adding new timeframe, source-origin, or entry-mode phase target lists."


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


def _families_with_true(safety_manifest: Mapping[str, Any], key: str) -> list[str]:
    families: list[str] = []
    for family, settings in safety_manifest.items():
        if isinstance(settings, Mapping) and settings.get(key) is True:
            families.append(str(family))
    return sorted(families)


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(_sanitize(payload))
    return records


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_sanitize(child) for child in value]
    if isinstance(value, tuple):
        return [_sanitize(child) for child in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
