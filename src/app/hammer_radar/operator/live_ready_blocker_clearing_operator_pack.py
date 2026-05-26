"""R139 live-ready blocker clearing operator pack.

This module turns the R138 autonomous-lane burn-down into an ordered operator
pack. It is diagnostic only: it never executes generated commands, creates
payloads, signs requests, calls Binance, mutates env/config, or places orders.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.autonomous_lane_live_ready_burn_down import (
    DEFAULT_LANE_KEY,
    SAFETY as R138_SAFETY,
    build_autonomous_lane_live_ready_burn_down,
)
from src.app.hammer_radar.operator.burn_down_command_pack_sanity import (
    COMMAND_PACK_SAFE,
    build_burn_down_command_pack_sanity,
)

BLOCKER_CLEARING_PACK_READY = "BLOCKER_CLEARING_PACK_READY"
BLOCKER_CLEARING_PACK_BLOCKED = "BLOCKER_CLEARING_PACK_BLOCKED"
BLOCKER_CLEARING_PACK_REJECTED = "BLOCKER_CLEARING_PACK_REJECTED"
BLOCKER_CLEARING_PACK_ERROR = "BLOCKER_CLEARING_PACK_ERROR"

EVENT_TYPE = "LIVE_READY_BLOCKER_CLEARING_OPERATOR_PACK"
LEDGER_FILENAME = "live_ready_blocker_clearing_operator_packs.ndjson"
CONFIRM_OPERATOR_PACK_RECORDING_PHRASE = (
    "I CONFIRM BLOCKER CLEARING OPERATOR PACK RECORDING ONLY; NO ORDER; NO BINANCE CALL."
)

SAFE_READ_ONLY = "SAFE_READ_ONLY"
SAFE_PREVIEW = "SAFE_PREVIEW"
SAFE_RECORD_EVIDENCE_WITH_CONFIRMATION = "SAFE_RECORD_EVIDENCE_WITH_CONFIRMATION"
FUTURE_EXPLICIT_APPLY_ONLY = "FUTURE_EXPLICIT_APPLY_ONLY"
FUTURE_PHASE_ONLY = "FUTURE_PHASE_ONLY"
FORBIDDEN = "FORBIDDEN"
COMMAND_TYPES = {
    SAFE_READ_ONLY,
    SAFE_PREVIEW,
    SAFE_RECORD_EVIDENCE_WITH_CONFIRMATION,
    FUTURE_EXPLICIT_APPLY_ONLY,
    FUTURE_PHASE_ONLY,
    FORBIDDEN,
}

SAFETY = {
    **R138_SAFETY,
    "order_payload_created": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "config_written": False,
    "global_live_flags_changed": False,
}

RUNNABLE_FORBIDDEN_TERMS = (
    "execute_live_order",
    "live-connector-submit",
    "submit_test_order",
    "submit_protective_test",
    "build_signed",
    "signature",
    "BINANCE_API_SECRET",
    "BINANCE_API_KEY=",
    "/fapi/v1/order",
    "--apply",
    "--apply-lane-mode-change",
    "sed -i",
    "export ",
    "systemctl",
    "sudo",
    "HAMMER_ALLOW_LIVE_ORDERS=true",
    "HAMMER_GLOBAL_KILL_SWITCH=false",
)

SOURCE_SURFACES_USED = [
    "operator.autonomous_lane_live_ready_burn_down.build_autonomous_lane_live_ready_burn_down",
    "operator.burn_down_command_pack_sanity.build_burn_down_command_pack_sanity",
    "operator.lane_control_cockpit build/read-only CLI surface",
    "operator.lane_command_interface R124 preview semantics",
    "operator.autonomous_paper_lane_executor_integration R129 paper-only command templates",
    "operator.first_tiny_live_autonomous_lane_authorization R130 preview/record templates",
    "operator.first_tiny_live_lane_execution_gate R126 recheck",
    "operator.live_lane_kill_switch_rehearsal R131 recheck",
    "operator.live_adapter_boundary_final_review R132 boundary recheck",
    "operator.first_tiny_live_order_payload_dry_authorization R134 dry authorization check",
    "operator.live_adapter_execution_rehearsal R135 rehearsal check",
    "operator.protective_order_dry_policy_review R136 policy review",
    "operator.protective_payload_dry_preview_boundary R137 preview boundary",
    "operator.final_live_preflight R102 final preflight",
    "operator.first_live_activation_gate R106 first-live activation gate",
    "operator.live_env_boundary_review",
    "operator.live_arming_preflight",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_live_ready_blocker_clearing_operator_pack(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    record_pack: bool = False,
    confirm_operator_pack: str | None = None,
    burn_down: Mapping[str, Any] | None = None,
    source_statuses: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    try:
        resolved_log_dir = get_log_dir(log_dir, use_env=True)
        burn_down_payload = (
            dict(burn_down)
            if burn_down is not None
            else build_autonomous_lane_live_ready_burn_down(
                log_dir=resolved_log_dir,
                lane_key=lane_key,
                source_statuses=source_statuses,
                now=generated_at,
            )
        )
        command_sanity = build_burn_down_command_pack_sanity(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            source_statuses=source_statuses,
        )
        stages = build_clearing_stages_from_burn_down(burn_down_payload)
        expected_state_progression = build_expected_state_progression(stages=stages, burn_down=burn_down_payload)
        rollback_notes = build_rollback_and_stop_notes(stages=stages)
        probability_ladder = _probability_ladder_from_stages(stages)
        forbidden_actions = _forbidden_actions()
        warnings = _operator_warnings(command_sanity)
        safety_validation = validate_operator_pack_safety(
            {
                "stages": stages,
                "forbidden_actions": forbidden_actions,
                "safety": dict(SAFETY),
                "command_sanity": command_sanity,
            }
        )
        safe_to_generate = bool(safety_validation["safe_to_generate"])
        status = BLOCKER_CLEARING_PACK_READY if safe_to_generate else BLOCKER_CLEARING_PACK_BLOCKED
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "lane_key": str(burn_down_payload.get("lane_key") or lane_key),
                "live_ready_now": False,
                "stages": stages,
                "next_three_actions": _next_three_actions(stages),
                "expected_state_progression": expected_state_progression,
                "probability_ladder": probability_ladder,
                "forbidden_actions": forbidden_actions,
                "operator_warnings": warnings,
                "rollback_and_stop_notes": rollback_notes,
                "pack_safety_validation": safety_validation,
                "record_pack_requested": bool(record_pack),
                "confirmation_valid": False,
                "pack_recorded": False,
                "pack_id": None,
                "safety": dict(SAFETY),
                "source_surfaces_used": _source_surfaces(burn_down_payload),
            }
        )
        if not record_pack:
            return payload
        if confirm_operator_pack != CONFIRM_OPERATOR_PACK_RECORDING_PHRASE:
            return _sanitize(
                {
                    **payload,
                    "status": BLOCKER_CLEARING_PACK_REJECTED,
                    "record_pack_requested": True,
                    "confirmation_valid": False,
                    "pack_recorded": False,
                    "recording_blockers": ["exact R139 operator-pack recording confirmation phrase is required"],
                }
            )
        if not safe_to_generate:
            return _sanitize(
                {
                    **payload,
                    "status": BLOCKER_CLEARING_PACK_BLOCKED,
                    "record_pack_requested": True,
                    "confirmation_valid": True,
                    "pack_recorded": False,
                    "recording_blockers": ["operator pack safety validation did not pass"],
                }
            )
        record = append_blocker_clearing_operator_pack_record(payload, log_dir=resolved_log_dir)
        return _sanitize(
            {
                **payload,
                "record_pack_requested": True,
                "confirmation_valid": True,
                "pack_recorded": True,
                "pack_id": record["pack_id"],
                "ledger_path": str(blocker_clearing_operator_pack_records_path(resolved_log_dir)),
            }
        )
    except Exception as exc:  # pragma: no cover - defensive diagnostic boundary
        return _sanitize(
            {
                "status": BLOCKER_CLEARING_PACK_ERROR,
                "generated_at": generated_at.isoformat(),
                "lane_key": lane_key,
                "live_ready_now": False,
                "stages": [],
                "next_three_actions": [],
                "expected_state_progression": [],
                "probability_ladder": [],
                "forbidden_actions": _forbidden_actions(),
                "operator_warnings": [f"operator pack generation failed: {exc.__class__.__name__}"],
                "rollback_and_stop_notes": build_rollback_and_stop_notes(stages=[]),
                "pack_safety_validation": {"safe_to_generate": False, "findings": ["generation_error"]},
                "record_pack_requested": bool(record_pack),
                "confirmation_valid": False,
                "pack_recorded": False,
                "pack_id": None,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_clearing_stages_from_burn_down(burn_down: Mapping[str, Any]) -> list[dict[str, Any]]:
    command_pack = _mapping(burn_down.get("operator_command_pack"))
    lane_key = str(burn_down.get("lane_key") or DEFAULT_LANE_KEY)
    stage_specs = [
        (
            1,
            "Visibility and current truth",
            "Refresh cockpit, burn-down, command-pack sanity, lane, and router state before touching evidence.",
            "This prevents clearing stale blockers or acting on an outdated lane/router state.",
            [
                "Use local CLI only.",
                "Do not execute generated commands automatically.",
                "No ledger write is required for this stage.",
            ],
            [
                _cmd("Cockpit state", SAFE_READ_ONLY, _inspect("lane-control-cockpit-state"), "Current read-only cockpit state is visible.", False, "Read-only UI/CLI state only."),
                _cmd("R138 burn-down", SAFE_READ_ONLY, command_pack.get("autonomous_lane_live_ready_burn_down"), "Current ranked blockers and clear order are visible.", False, "R138 remains diagnostic only."),
                _cmd("R138.5 command pack sanity", SAFE_READ_ONLY, _inspect(f"burn-down-command-pack-sanity --lane-key {json.dumps(lane_key)}"), "Unsafe command count is zero before using templates.", False, "Does not write ledgers."),
                _cmd("Lane status", SAFE_READ_ONLY, command_pack.get("lane_control_status"), "Selected lane status and mode are visible.", False, "No mode apply is performed."),
                _cmd("Router status", SAFE_READ_ONLY, command_pack.get("fresh_signal_router_status"), "Fresh routed candidate state is visible.", False, "Router status is diagnostic only."),
            ],
            ["R138 and R138.5 run successfully.", "The next blocker to clear is still paper proof or lane intent."],
            20,
        ),
        (
            2,
            "Paper proof",
            "Preview and, only with the R129 phrase, record autonomous paper proof evidence.",
            "Recent autonomous paper evidence is the last non-executing proof layer before tiny-live gate review.",
            ["Stage 1 completed.", "A fresh routed candidate exists or the operator accepts waiting for one."],
            [
                _cmd("Preview R129 paper executor integration", SAFE_PREVIEW, command_pack.get("autonomous_paper_lane_executor_integration_preview"), "Shows paper-only integration blockers and preview records.", False, "Preview does not write paper proof."),
                _cmd("Record R129 paper proof template", SAFE_RECORD_EVIDENCE_WITH_CONFIRMATION, command_pack.get("autonomous_paper_lane_executor_integration_record_template"), "Appends R129 paper-only evidence when its exact phrase is supplied.", False, "Records paper integration only; no Binance, no order payload."),
                _cmd("Verify paper proof after recording", SAFE_READ_ONLY, command_pack.get("autonomous_paper_lane_executor_integration_preview"), "R129/R138 should show paper proof reduced after a valid record.", False, "Verification remains read-only unless the operator separately records R129."),
            ],
            ["Recent autonomous paper proof is present for the selected lane.", "R138 paper-proof blocker is reduced or explained."],
            30,
        ),
        (
            3,
            "Lane tiny_live intent",
            "Preview lane mode and lane authorization state without applying config changes.",
            "Tiny-live intent must stay explicit and separate from diagnostics.",
            ["Stage 2 paper proof is present or the pack remains blocked at paper proof."],
            [
                _cmd("Preview lane tiny_live mode request", SAFE_PREVIEW, command_pack.get("lane_tiny_live_mode_preview"), "Shows R124 lane tiny_live request preview.", False, "Preview only; do not apply lane config in R139."),
                _cmd("Preview R130 lane authorization", SAFE_PREVIEW, command_pack.get("first_tiny_live_autonomous_lane_authorization_preview"), "Shows R130 authorization readiness and blockers.", False, "R130 preview is not authorization."),
                _cmd("Future explicit lane mode apply", FUTURE_EXPLICIT_APPLY_ONLY, None, "A later explicit operator action may use R124 confirmation to apply lane mode.", True, "Do not run in R139; config mutation is outside this phase."),
                _cmd("Future explicit R130 authorization record", FUTURE_EXPLICIT_APPLY_ONLY, command_pack.get("first_tiny_live_autonomous_lane_authorization_record_template"), "A later explicit authorization-intent record may be appended when R130 prerequisites are clear.", True, "Do not treat this as order authorization."),
            ],
            ["Lane tiny_live intent is previewed.", "Any apply/authorization record remains explicitly withheld until operator confirmation."],
            44,
        ),
        (
            4,
            "Tiny-live gate recheck",
            "Recheck the lane gate, authorization, kill-switch rehearsal, and adapter boundary.",
            "These surfaces prove tiny-live remains behind gate composition and rollback review.",
            ["Paper proof and lane intent have been previewed.", "No env or config mutation is performed by R139."],
            [
                _cmd("R126 gate check", SAFE_READ_ONLY, command_pack.get("first_tiny_live_lane_execution_gate"), "Tiny-live lane gate status is refreshed.", False, "Gate review only; no execution."),
                _cmd("R130 authorization check", SAFE_PREVIEW, command_pack.get("first_tiny_live_autonomous_lane_authorization_preview"), "Authorization state is refreshed.", False, "Authorization remains intent-only."),
                _cmd("R131 kill-switch rehearsal", SAFE_PREVIEW, command_pack.get("live_lane_kill_switch_rehearsal"), "Kill-switch and rollback rehearsal state is visible.", False, "No service or lane mutation is performed."),
                _cmd("R132 adapter boundary review", SAFE_PREVIEW, command_pack.get("live_adapter_boundary_final_review"), "Live adapter boundary blockers are refreshed.", False, "No adapter behavior is implemented."),
            ],
            ["R126/R130/R131/R132 blockers are known after paper/lane updates.", "No live execution authority is created."],
            52,
        ),
        (
            5,
            "Protective readiness",
            "Recheck protective policy and dry preview boundaries and identify stop/take-profit gaps.",
            "Tiny-live cannot proceed without audited protective-order policy boundaries.",
            ["Stage 4 rechecks are complete.", "No protective order endpoint or payload generation is allowed."],
            [
                _cmd("R136 protective policy review", SAFE_PREVIEW, command_pack.get("protective_order_dry_policy_review"), "Stop/take-profit policy readiness is visible.", False, "Policy review only; no protective payload."),
                _cmd("R137 protective payload dry preview boundary", SAFE_PREVIEW, command_pack.get("protective_payload_dry_preview_boundary"), "Abstract dry preview boundary state is visible.", False, "Boundary review only; no executable protective payload."),
                _cmd("Identify missing stop/take-profit references", SAFE_READ_ONLY, command_pack.get("protective_order_dry_policy_review"), "Missing stop or take-profit references are named through R136/R137 blockers.", False, "Use existing R136/R137 blockers as source of truth."),
            ],
            ["Stop and take-profit policy references are present or blockers are explicitly named.", "Protective preview remains non-executable."],
            60,
        ),
        (
            6,
            "Credentials and adapter boundary",
            "Check credential presence booleans and adapter boundary without secrets, network, or signing.",
            "Credential presence can be reviewed without exposing values or contacting Binance.",
            ["Protective readiness has been reviewed.", "Only presence booleans may be reported."],
            [
                _cmd("Credential presence booleans only", SAFE_READ_ONLY, command_pack.get("final_live_preflight"), "Credential presence is reported as true/false only.", False, "Do not print env values or secrets."),
                _cmd("R132 adapter boundary", SAFE_PREVIEW, command_pack.get("live_adapter_boundary_final_review"), "Adapter boundary is rechecked after credential/protective review.", False, "No network or signed requests."),
                _cmd("Future configured live adapter", FUTURE_PHASE_ONLY, None, "A later explicit phase must configure any live adapter behavior.", True, "R139 cannot implement or enable live adapter execution."),
            ],
            ["Credential boundary is known as booleans only.", "Adapter boundary remains non-executing."],
            66,
        ),
        (
            7,
            "Global gates",
            "Recheck final preflight, R106, live env boundary, arming preflight, and kill-switch state.",
            "Global gates remain authoritative above lane-level readiness.",
            ["No env mutation is authorized.", "Global kill switch and live flags are not changed by R139."],
            [
                _cmd("Final live preflight", SAFE_READ_ONLY, command_pack.get("final_live_preflight"), "R102 final preflight state is visible.", False, "Read-only preflight only."),
                _cmd("First-live activation gate", SAFE_READ_ONLY, command_pack.get("first_live_activation_gate"), "R106 activation gate state is visible.", False, "R106 readiness is not execution authority."),
                _cmd("Live env boundary review", SAFE_READ_ONLY, _inspect("live-env-boundary-review"), "Live env boundary state is visible.", False, "No env writes."),
                _cmd("Live arming preflight", SAFE_READ_ONLY, _inspect("live-arming-preflight"), "Live arming blockers are visible.", False, "No live flags changed."),
                _cmd("Future kill-switch/live-flag changes", FUTURE_PHASE_ONLY, None, "Any live flag or kill-switch change requires a future explicit phase.", True, "Do not disable kill switch or enable live flags in R139."),
            ],
            ["Global gate blockers are refreshed.", "Env and global live flags remain unchanged."],
            72,
        ),
        (
            8,
            "Dry authorization readiness",
            "Recheck dry authorization and adapter rehearsal readiness for future R140/R141 planning.",
            "Dry authorization is still non-executing and must precede any future payload work.",
            ["Global gate state has been reviewed.", "No payload creation is allowed."],
            [
                _cmd("R134 dry authorization check", SAFE_PREVIEW, command_pack.get("first_tiny_live_order_payload_dry_authorization"), "Dry authorization readiness and blockers are visible.", False, "No executable payload is created."),
                _cmd("R135 adapter rehearsal check", SAFE_PREVIEW, _inspect(f"live-adapter-execution-rehearsal --lane-key {json.dumps(lane_key)}"), "Adapter rehearsal readiness is visible.", False, "No network, no signing, no adapter execution."),
                _cmd("Identify R140/R141 readiness", SAFE_READ_ONLY, command_pack.get("autonomous_lane_live_ready_burn_down"), "R138/R139 state indicates whether safe clearing execution or later authorization planning can proceed.", False, "Planning only."),
            ],
            ["R134/R135 blockers are known.", "R140 can execute safe clearing checks only if no earlier blocker is ambiguous."],
            82,
        ),
        (
            9,
            "Future explicit live authorization",
            "List future-only live authorization requirements without offering a current live command.",
            "Actual live authorization must be separate, explicit, and future-scoped.",
            ["R139 pack has been recorded only if the operator used the R139 phrase.", "All current commands remain non-executing."],
            [
                _cmd("Future phase must request explicit live authorization", FUTURE_PHASE_ONLY, None, "A later phase must define exact authorization, risk, protective, rollback, and postmortem requirements.", True, "No current live command exists in this pack."),
                _cmd("Final operator confirmation required later", FUTURE_PHASE_ONLY, None, "Future confirmation must be separate from R139 pack recording.", True, "R139 confirmation records the pack only."),
                _cmd("Forbidden live execution now", FORBIDDEN, None, "Live execution, Binance calls, signed requests, and payload creation remain forbidden now.", True, "Do not run any live order command."),
            ],
            ["No current live execution path is present.", "Future authorization remains separate from blocker clearing."],
            88,
        ),
    ]
    return [
        _stage(stage_no, title, objective, why, preconditions, commands, exit_criteria, probability)
        for stage_no, title, objective, why, preconditions, commands, exit_criteria, probability in stage_specs
    ]


def build_safe_operator_commands_for_stage(stage: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(command)
        for command in stage.get("commands") or []
        if isinstance(command, Mapping) and command.get("command_type") in {SAFE_READ_ONLY, SAFE_PREVIEW, SAFE_RECORD_EVIDENCE_WITH_CONFIRMATION}
    ]


def classify_commands_as_safe_preview_record_or_future_only(commands: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    for command in commands:
        item = dict(command)
        command_type = str(item.get("command_type") or "").strip()
        rendered = str(item.get("command") or "")
        if command_type not in COMMAND_TYPES:
            if "confirm-" in rendered or "--record-" in rendered:
                command_type = SAFE_RECORD_EVIDENCE_WITH_CONFIRMATION
            elif rendered:
                command_type = SAFE_READ_ONLY
            else:
                command_type = FUTURE_PHASE_ONLY
        if rendered and _has_forbidden_runnable_term(rendered) and command_type != FUTURE_EXPLICIT_APPLY_ONLY:
            command_type = FORBIDDEN
            item["do_not_run_now"] = True
        item["command_type"] = command_type
        classified.append(item)
    return classified


def build_expected_state_progression(
    *,
    stages: list[Mapping[str, Any]],
    burn_down: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    ranked_count = len(list((burn_down or {}).get("ranked_blockers") or []))
    return [
        {
            "stage_no": int(stage.get("stage_no") or 0),
            "title": stage.get("title"),
            "expected_state_movement": _state_movement_for_stage(int(stage.get("stage_no") or 0)),
            "burn_down_blockers_before_estimate": ranked_count if stage.get("stage_no") == 1 else None,
            "live_ready_now": False,
        }
        for stage in stages
    ]


def build_rollback_and_stop_notes(*, stages: list[Mapping[str, Any]] | None = None) -> list[str]:
    return [
        "Stop immediately if any generated command would place an order, call Binance, sign a request, create an executable payload, mutate env/config, restart services, or disable the kill switch.",
        "If a read-only recheck reports unsafe safety flags, do not continue; return to R138 burn-down and R138.5 command-pack sanity.",
        "If R129 evidence cannot be recorded safely, wait for a fresh routed candidate and keep the lane paper/shadow only.",
        "If lane tiny_live intent is needed, use only R124/R130 preview in R139; any apply/authorization record remains a separate explicit operator action.",
        "If global gates remain blocked, do not work around them; R106/global gates stay authoritative.",
    ]


def validate_operator_pack_safety(pack: Mapping[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for stage in pack.get("stages") or []:
        for command in _mapping(stage).get("commands") or []:
            if not isinstance(command, Mapping):
                findings.append({"finding": "command_not_mapping"})
                continue
            command_type = str(command.get("command_type") or "")
            rendered = str(command.get("command") or "")
            do_not_run_now = bool(command.get("do_not_run_now"))
            if command_type not in COMMAND_TYPES:
                findings.append({"finding": "unknown_command_type", "label": command.get("label")})
            if command_type in {FUTURE_EXPLICIT_APPLY_ONLY, FUTURE_PHASE_ONLY, FORBIDDEN} and not do_not_run_now:
                findings.append({"finding": "future_or_forbidden_command_runnable", "label": command.get("label")})
            if rendered and command_type != FUTURE_EXPLICIT_APPLY_ONLY and _has_forbidden_runnable_term(rendered):
                findings.append({"finding": "runnable_command_contains_forbidden_term", "label": command.get("label"), "command": rendered})
    safety = _mapping(pack.get("safety") or SAFETY)
    for key, value in safety.items():
        if key == "paper_live_separation_intact":
            if value is not True:
                findings.append({"finding": "paper_live_separation_not_intact"})
        elif value is not False:
            findings.append({"finding": "unsafe_safety_flag", "key": key, "value": value})
    command_sanity = _mapping(pack.get("command_sanity"))
    if command_sanity and command_sanity.get("status") != COMMAND_PACK_SAFE:
        findings.append({"finding": "r138_5_command_pack_sanity_not_safe", "status": command_sanity.get("status")})
    return {
        "safe_to_generate": not findings,
        "findings": findings,
        "runnable_command_count": _runnable_command_count(pack.get("stages") or []),
        "future_only_command_count": _future_only_command_count(pack.get("stages") or []),
        "forbidden_command_count": _forbidden_command_count(pack.get("stages") or []),
    }


def append_blocker_clearing_operator_pack_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = blocker_clearing_operator_pack_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "pack_id": str(record.get("pack_id") or f"r139_operator_pack_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "lane_key": record.get("lane_key"),
            "stages": list(record.get("stages") or []),
            "next_three_actions": list(record.get("next_three_actions") or []),
            "expected_state_progression": list(record.get("expected_state_progression") or []),
            "probability_ladder": list(record.get("probability_ladder") or []),
            "forbidden_actions": list(record.get("forbidden_actions") or []),
            "operator_warnings": list(record.get("operator_warnings") or []),
            "rollback_and_stop_notes": list(record.get("rollback_and_stop_notes") or []),
            "safety": record.get("safety") or dict(SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or []),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_blocker_clearing_operator_pack_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
    lane_key: str | None = None,
) -> list[dict[str, Any]]:
    path = blocker_clearing_operator_pack_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if lane_key is not None and record.get("lane_key") != lane_key:
                continue
            records.append(_sanitize(record))
    if limit > 0:
        return list(reversed(records))[:limit]
    return records


def summarize_blocker_clearing_operator_packs(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    lane_counts = Counter(str(record.get("lane_key") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
        "last_pack_id": records[-1].get("pack_id") if records else None,
        "safety": dict(SAFETY),
    }


def format_live_ready_blocker_clearing_operator_pack_json(payload: Mapping[str, Any]) -> str:
    compact = {
        "status": payload.get("status"),
        "generated_at": payload.get("generated_at"),
        "lane_key": payload.get("lane_key"),
        "live_ready_now": bool(payload.get("live_ready_now")),
        "stages": list(payload.get("stages") or []),
        "next_three_actions": list(payload.get("next_three_actions") or [])[:3],
        "expected_state_progression": list(payload.get("expected_state_progression") or []),
        "probability_ladder": list(payload.get("probability_ladder") or []),
        "forbidden_actions": list(payload.get("forbidden_actions") or []),
        "operator_warnings": list(payload.get("operator_warnings") or []),
        "rollback_and_stop_notes": list(payload.get("rollback_and_stop_notes") or []),
        "pack_safety_validation": payload.get("pack_safety_validation") or {},
        "record_pack_requested": bool(payload.get("record_pack_requested", False)),
        "confirmation_valid": bool(payload.get("confirmation_valid", False)),
        "pack_recorded": bool(payload.get("pack_recorded", False)),
        "pack_id": payload.get("pack_id"),
        "recording_blockers": list(payload.get("recording_blockers") or []),
        "safety": payload.get("safety") or dict(SAFETY),
        "source_surfaces_used": list(payload.get("source_surfaces_used") or []),
    }
    return json.dumps(_sanitize(compact), sort_keys=True, separators=(",", ":"))


def blocker_clearing_operator_pack_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _stage(
    stage_no: int,
    title: str,
    objective: str,
    why: str,
    preconditions: list[str],
    commands: list[dict[str, Any]],
    exit_criteria: list[str],
    probability_after_stage_pct: int,
) -> dict[str, Any]:
    return {
        "stage_no": stage_no,
        "title": title,
        "objective": objective,
        "why_this_stage_matters": why,
        "preconditions": preconditions,
        "commands": classify_commands_as_safe_preview_record_or_future_only(commands),
        "exit_criteria": exit_criteria,
        "probability_after_stage_pct": min(100, max(0, int(probability_after_stage_pct))),
    }


def _cmd(
    label: str,
    command_type: str,
    command: str | None,
    expected_result: str,
    do_not_run_now: bool,
    safety_note: str,
) -> dict[str, Any]:
    return {
        "label": label,
        "command_type": command_type,
        "command": command,
        "expected_result": expected_result,
        "do_not_run_now": do_not_run_now,
        "safety_note": safety_note,
    }


def _inspect(command: str) -> str:
    return f"PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward {command}"


def _next_three_actions(stages: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    preferred_labels = [
        "R138 burn-down",
        "Preview R129 paper executor integration",
        "Record R129 paper proof template",
    ]
    for label in preferred_labels:
        for stage in stages:
            for command in stage.get("commands") or []:
                if not isinstance(command, Mapping) or command.get("label") != label:
                    continue
                if command.get("do_not_run_now") is True:
                    continue
                if command.get("command_type") not in {SAFE_READ_ONLY, SAFE_PREVIEW, SAFE_RECORD_EVIDENCE_WITH_CONFIRMATION}:
                    continue
                actions.append(
                    {
                        "rank": len(actions) + 1,
                        "stage_no": stage.get("stage_no"),
                        "action": command.get("label"),
                        "command_type": command.get("command_type"),
                        "command": command.get("command"),
                        "why": command.get("safety_note"),
                    }
                )
                break
            if len(actions) == len(preferred_labels):
                break
    return actions[:3]


def _probability_ladder_from_stages(stages: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "stage_no": stage.get("stage_no"),
            "title": stage.get("title"),
            "probability_pct": min(100, max(0, int(stage.get("probability_after_stage_pct") or 0))),
            "basis": "heuristic_conservative",
            "operator_note": f"After completing stage {stage.get('stage_no')}: {stage.get('title')}.",
        }
        for stage in stages
    ]


def _forbidden_actions() -> list[dict[str, Any]]:
    labels = [
        "Place a real order",
        "Create an executable Binance order payload",
        "Create an executable protective order payload",
        "Call Binance order or test-order endpoints",
        "Call protective order endpoints",
        "Create signed request material",
        "Print secrets or env values",
        "Mutate env files or live flags",
        "Mutate lane config from R139",
        "Disable the global kill switch",
        "Restart or install services",
    ]
    return [{"action": label, "command_type": FORBIDDEN, "command": None, "do_not_run_now": True} for label in labels]


def _operator_warnings(command_sanity: Mapping[str, Any]) -> list[str]:
    warnings = [
        "R139 records the operator pack only; it does not execute any generated command.",
        "R139 READY means the pack was generated safely, not that live trading is ready.",
        "Record-evidence commands require their own exact phase confirmation phrases.",
        "Future-only actions must remain unrun until a later explicit phase authorizes them.",
    ]
    if command_sanity.get("status") != COMMAND_PACK_SAFE:
        warnings.append("R138.5 command-pack sanity is not safe; do not use generated commands until repaired.")
    return warnings


def _state_movement_for_stage(stage_no: int) -> str:
    movements = {
        1: "Current truth refreshed; no blockers cleared yet.",
        2: "Paper-proof blocker may move from missing to evidenced after explicit R129 recording.",
        3: "Lane tiny_live intent becomes explicit; config apply remains future-only.",
        4: "R126/R130/R131/R132 blockers become current after paper/lane updates.",
        5: "Protective stop/take-profit blockers become named or ready through R136/R137.",
        6: "Credential and adapter boundary state becomes known without secrets or network.",
        7: "Global gate blockers are refreshed while kill switch and live flags stay unchanged.",
        8: "Dry authorization and adapter rehearsal readiness indicate whether R140/R141 can proceed.",
        9: "Live authorization remains future-only with no current live command.",
    }
    return movements.get(stage_no, "No state movement defined.")


def _source_surfaces(burn_down: Mapping[str, Any]) -> list[str]:
    surfaces = list(SOURCE_SURFACES_USED)
    for item in burn_down.get("source_surfaces_used") or []:
        text = str(item)
        if text not in surfaces:
            surfaces.append(text)
    return surfaces


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _has_forbidden_runnable_term(command: str) -> bool:
    return any(term in command for term in RUNNABLE_FORBIDDEN_TERMS)


def _runnable_command_count(stages: list[Any]) -> int:
    return sum(
        1
        for stage in stages
        for command in _mapping(stage).get("commands") or []
        if isinstance(command, Mapping) and command.get("command") and not command.get("do_not_run_now")
    )


def _future_only_command_count(stages: list[Any]) -> int:
    return sum(
        1
        for stage in stages
        for command in _mapping(stage).get("commands") or []
        if isinstance(command, Mapping) and command.get("command_type") in {FUTURE_EXPLICIT_APPLY_ONLY, FUTURE_PHASE_ONLY}
    )


def _forbidden_command_count(stages: list[Any]) -> int:
    return sum(
        1
        for stage in stages
        for command in _mapping(stage).get("commands") or []
        if isinstance(command, Mapping) and command.get("command_type") == FORBIDDEN
    )


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_sanitize(child) for child in value]
    if isinstance(value, tuple):
        return [_sanitize(child) for child in value]
    if isinstance(value, Path):
        return str(value)
    return value
