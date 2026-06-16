"""R281 Binance account-read env discovery contract.

This module discovers credential variable names and presence only. It never
prints or returns raw env values and it does not call Binance.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.binance_live_status import (
    ENV_ALLOW_LIVE_ORDERS,
    ENV_BINANCE_LIVE_ENABLED,
    ENV_GLOBAL_KILL_SWITCH,
    ENV_LIVE_EXECUTION_ENABLED,
)
from src.app.hammer_radar.operator.binance_readonly import (
    ENV_API_KEY,
    ENV_API_SECRET,
    ENV_CONNECTOR_MODE,
    ENV_LIVE_TRADING_ENABLED,
)
from src.app.hammer_radar.operator.env_role_adapter import (
    ACCOUNT_READ_KEY_VAR,
    ACCOUNT_READ_SECRET_VAR,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE

EVENT_TYPE = "BINANCE_ACCOUNT_READ_ENV_DISCOVERY"

ACCOUNT_READ_ENV_READY = "ACCOUNT_READ_ENV_READY"
ACCOUNT_READ_ENV_MISSING = "ACCOUNT_READ_ENV_MISSING"
ACCOUNT_READ_ENV_ALIAS_PRESENT_BUT_NOT_MARKED_READ_ONLY = (
    "ACCOUNT_READ_ENV_ALIAS_PRESENT_BUT_NOT_MARKED_READ_ONLY"
)
ACCOUNT_READ_ENV_PARTIAL = "ACCOUNT_READ_ENV_PARTIAL"

CANONICAL_ENABLED_ENV = "HAMMER_BINANCE_ACCOUNT_READ_ENABLED"
CANONICAL_MODE_ENV = "HAMMER_BINANCE_ACCOUNT_READ_MODE"
CANONICAL_API_KEY_ENV = "HAMMER_BINANCE_ACCOUNT_READ_API_KEY"
CANONICAL_API_SECRET_ENV = "HAMMER_BINANCE_ACCOUNT_READ_API_SECRET"
HAMMER_RADAR_CONFIG_DIR = Path("/home/josue/.config/hammer-radar")
KNOWN_SAFE_READONLY_ENV_FILE = HAMMER_RADAR_CONFIG_DIR / "binance-readonly.env"

READ_ONLY_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}
READ_ONLY_MODE_VALUES = {"read_only", "readonly"}
LIVE_FALSE_VALUES = {"0", "false", "no", "off", "disabled"}

ROLE_SPECIFIC_KEY_ENV = ACCOUNT_READ_KEY_VAR
ROLE_SPECIFIC_SECRET_ENV = ACCOUNT_READ_SECRET_VAR

ALIAS_CANDIDATE_PAIRS = [
    (ROLE_SPECIFIC_KEY_ENV, ROLE_SPECIFIC_SECRET_ENV, "role_specific"),
    ("HAMMER_BINANCE_READONLY_API_KEY", "HAMMER_BINANCE_READONLY_API_SECRET", "alias"),
    ("HAMMER_BINANCE_READ_ONLY_API_KEY", "HAMMER_BINANCE_READ_ONLY_API_SECRET", "alias"),
    ("HAMMER_BINANCE_API_KEY", "HAMMER_BINANCE_API_SECRET", "generic_alias"),
    ("BINANCE_FUTURES_API_KEY", "BINANCE_FUTURES_API_SECRET", "generic_alias"),
    (ENV_API_KEY, ENV_API_SECRET, "legacy_readonly_alias"),
]

RUNTIME_SAFETY_ENV_NAMES = [
    CANONICAL_ENABLED_ENV,
    CANONICAL_MODE_ENV,
    ENV_CONNECTOR_MODE,
    ENV_LIVE_TRADING_ENABLED,
    ENV_BINANCE_LIVE_ENABLED,
    ENV_LIVE_EXECUTION_ENABLED,
    ENV_ALLOW_LIVE_ORDERS,
    ENV_GLOBAL_KILL_SWITCH,
]

DISCOVERY_ENV_NAME_ALLOWLIST = [
    CANONICAL_ENABLED_ENV,
    CANONICAL_MODE_ENV,
    CANONICAL_API_KEY_ENV,
    CANONICAL_API_SECRET_ENV,
    *RUNTIME_SAFETY_ENV_NAMES,
    *[name for pair in ALIAS_CANDIDATE_PAIRS for name in pair[:2]],
]

RUNTIME_ENV_FILE_LOAD_ALLOWLIST = [
    ENV_API_KEY,
    ENV_API_SECRET,
    ENV_CONNECTOR_MODE,
    ENV_LIVE_TRADING_ENABLED,
    CANONICAL_API_KEY_ENV,
    CANONICAL_API_SECRET_ENV,
    CANONICAL_MODE_ENV,
    CANONICAL_ENABLED_ENV,
]

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "network_allowed": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "leverage_change_called": False,
    "margin_change_called": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "api_key_used": False,
    "api_secret_used": False,
    "selected_env_values_redacted": True,
    "secret_values_in_output": False,
    "secrets_shown": False,
    "final_command_available": False,
    "submit_allowed": False,
    "real_order_forbidden": True,
}


def build_binance_account_read_env_discovery(
    *,
    env: Mapping[str, str] | None = None,
    include_systemd: bool = True,
    load_discovered_binance_readonly_env: bool = False,
    binance_readonly_env_file: str | Path | None = None,
) -> dict[str, Any]:
    loaded_summary = build_loaded_env_summary(load_requested=False)
    if load_discovered_binance_readonly_env or binance_readonly_env_file is not None:
        target_path = binance_readonly_env_file
        if target_path is None:
            discovered = discover_systemd_env_files_for_hammer_approval_api()
            allowed = _allowed_runtime_env_file_paths(discovered)
            target_path = allowed[0] if allowed else KNOWN_SAFE_READONLY_ENV_FILE
        loaded_summary = load_allowed_readonly_env_file(target_path)
    source = os.environ if env is None else env
    canonical_pair = _pair_summary(
        source,
        CANONICAL_API_KEY_ENV,
        CANONICAL_API_SECRET_ENV,
        source_name="canonical",
    )
    alias_candidates = [
        _pair_summary(source, key, secret, source_name=source_name)
        for key, secret, source_name in ALIAS_CANDIDATE_PAIRS
    ]
    selected = _select_contract(source, canonical_pair, alias_candidates)
    status = _status_for_selection(canonical_pair, alias_candidates, selected)
    runtime_sources = _runtime_env_sources(source, include_systemd=include_systemd)
    blockers = _blockers_for_status(status, selected, canonical_pair, alias_candidates)
    if loaded_summary.get("loaded_env_file_status") not in {None, "NOT_REQUESTED", "LOADED"}:
        blockers = _dedupe([*blockers, str(loaded_summary.get("loaded_env_file_status"))])
    env_presence = {
        name: _presence(source, name)
        for name in _dedupe(
            [
                CANONICAL_ENABLED_ENV,
                CANONICAL_MODE_ENV,
                CANONICAL_API_KEY_ENV,
                CANONICAL_API_SECRET_ENV,
                *RUNTIME_SAFETY_ENV_NAMES,
                *[name for pair in ALIAS_CANDIDATE_PAIRS for name in pair[:2]],
            ]
        )
    }
    return _sanitize(
        {
            "event_type": EVENT_TYPE,
            "status": status,
            "canonical_env_contract": {
                "enabled_env_name": CANONICAL_ENABLED_ENV,
                "mode_env_name": CANONICAL_MODE_ENV,
                "api_key_env_name": CANONICAL_API_KEY_ENV,
                "api_secret_env_name": CANONICAL_API_SECRET_ENV,
                "api_key_present": canonical_pair["api_key_present"],
                "api_secret_present": canonical_pair["api_secret_present"],
                "enabled_present": _presence(source, CANONICAL_ENABLED_ENV),
                "mode_present": _presence(source, CANONICAL_MODE_ENV),
                "selected_env_values_redacted": True,
            },
            "discovered_alias_candidates": alias_candidates,
            "selected_env_contract": selected,
            "env_presence": env_presence,
            "runtime_env_sources": runtime_sources["runtime_env_sources"],
            "systemd_environment_files": runtime_sources["systemd_environment_files"],
            "candidate_env_file_paths": runtime_sources["candidate_env_file_paths"],
            "cli_runtime_env_loader_supported": True,
            "safe_cli_env_loader_command": (
                "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
                "--log-dir logs/hammer_radar_forward tiny-live-binance-account-read-env-discovery "
                "--load-discovered-binance-readonly-env"
            ),
            "allowed_env_file_paths": _allowed_runtime_env_file_paths(runtime_sources["systemd_environment_files"]),
            "loaded_env_file_status": loaded_summary.get("loaded_env_file_status"),
            "loaded_env_file_path": loaded_summary.get("loaded_env_file_path"),
            "loaded_env_names": loaded_summary.get("loaded_env_names", []),
            "ignored_env_names": loaded_summary.get("ignored_env_names", []),
            "loaded_secret_names_redacted": True,
            "env_file_values_printed": False,
            "env_file_values_redacted": True,
            "runtime_env_loader": loaded_summary,
            "safe_manual_fallback_template": {
                "path": "/home/josue/.config/hammer-radar/binance-readonly.env",
                "variables": [
                    "BINANCE_API_KEY=<redacted>",
                    "BINANCE_API_SECRET=<redacted>",
                    "BINANCE_CONNECTOR_MODE=read_only",
                    "BINANCE_LIVE_TRADING_ENABLED=false",
                ],
                "do_not_print_values": True,
            },
            "validation_commands": [
                (
                    "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
                    "--log-dir logs/hammer_radar_forward tiny-live-binance-account-read-env-discovery"
                ),
                "curl -s http://127.0.0.1:8015/tiny-live/binance-account-read-env-discovery | jq .status",
            ],
            "readiness_blockers": blockers,
            "safety": dict(SAFETY),
        }
    )


def adapt_env_for_selected_account_read_contract(*, env: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    adapted = {str(key): str(value) for key, value in source.items()}
    discovery = build_binance_account_read_env_discovery(env=source, include_systemd=False)
    selected = discovery.get("selected_env_contract") if isinstance(discovery.get("selected_env_contract"), Mapping) else {}
    if discovery.get("status") != ACCOUNT_READ_ENV_READY:
        return adapted
    key_name = str(selected.get("selected_api_key_env_name") or "")
    secret_name = str(selected.get("selected_api_secret_env_name") or "")
    if key_name and secret_name:
        adapted[ENV_API_KEY] = _env_value(source, key_name)
        adapted[ENV_API_SECRET] = _env_value(source, secret_name)
    adapted[ENV_CONNECTOR_MODE] = "read_only"
    adapted[ENV_LIVE_TRADING_ENABLED] = "false"
    return adapted


def discover_systemd_env_files_for_hammer_approval_api() -> list[str]:
    return _systemd_environment_files()


def parse_env_file_names_only(path: str | Path) -> dict[str, Any]:
    normalized = _normalize_runtime_env_file_path(path)
    if not normalized["allowed"]:
        return {
            "path": str(path),
            "allowed": False,
            "status": normalized["status"],
            "names": [],
            "values_redacted": True,
            "values_printed": False,
        }
    return {
        "path": normalized["path"],
        "allowed": True,
        "status": "PARSED_NAMES_ONLY",
        "names": _env_file_names(normalized["path"], allowed_names=RUNTIME_ENV_FILE_LOAD_ALLOWLIST),
        "values_redacted": True,
        "values_printed": False,
    }


def load_allowed_readonly_env_file(path: str | Path) -> dict[str, Any]:
    normalized = _normalize_runtime_env_file_path(path)
    if not normalized["allowed"]:
        return build_loaded_env_summary(
            load_requested=True,
            status=normalized["status"],
            path=str(path),
            blockers=[normalized["status"]],
        )
    resolved_path = Path(str(normalized["path"]))
    before_stat = _file_stat(resolved_path)
    parsed = _parse_env_file_allowed_values(resolved_path)
    overlay = {**os.environ, **parsed["values"]}
    mode = _env_value(overlay, ENV_CONNECTOR_MODE).lower() or _env_value(overlay, CANONICAL_MODE_ENV).lower()
    live = _env_value(overlay, ENV_LIVE_TRADING_ENABLED).lower()
    blockers: list[str] = []
    if mode not in READ_ONLY_MODE_VALUES:
        blockers.append("connector_mode_not_read_only")
    if live not in LIVE_FALSE_VALUES:
        blockers.append("live_trading_flag_not_false")
    if blockers:
        return build_loaded_env_summary(
            load_requested=True,
            status="BLOCKED_UNSAFE_ENV_VALUES",
            path=str(resolved_path),
            loaded_env_names=[],
            ignored_env_names=parsed["ignored_names"],
            blockers=blockers,
            file_stat_before=before_stat,
            file_stat_after=_file_stat(resolved_path),
        )
    for name, value in parsed["values"].items():
        os.environ[name] = value
    return build_loaded_env_summary(
        load_requested=True,
        status="LOADED",
        path=str(resolved_path),
        loaded_env_names=sorted(parsed["values"]),
        ignored_env_names=parsed["ignored_names"],
        blockers=[],
        file_stat_before=before_stat,
        file_stat_after=_file_stat(resolved_path),
    )


def build_loaded_env_summary(
    *,
    load_requested: bool,
    status: str | None = None,
    path: str | None = None,
    loaded_env_names: list[str] | None = None,
    ignored_env_names: list[str] | None = None,
    blockers: list[str] | None = None,
    file_stat_before: Mapping[str, Any] | None = None,
    file_stat_after: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    before = dict(file_stat_before or {})
    after = dict(file_stat_after or before)
    return {
        "load_requested": bool(load_requested),
        "loaded_env_file_status": status or ("NOT_REQUESTED" if not load_requested else "UNKNOWN"),
        "loaded_env_file_path": path,
        "loaded_env_names": sorted(_dedupe(loaded_env_names or [])),
        "ignored_env_names": sorted(_dedupe(ignored_env_names or [])),
        "loaded_secret_names_redacted": True,
        "env_file_values_printed": False,
        "secret_values_in_output": False,
        "secrets_shown": False,
        "env_written": False,
        "env_mutated": False,
        "env_file_modified": bool(before and after and before != after),
        "allowed_env_names": list(RUNTIME_ENV_FILE_LOAD_ALLOWLIST),
        "read_only_mode_required": True,
        "live_trading_false_required": True,
        "blockers": _dedupe(blockers or []),
    }


def format_binance_account_read_env_discovery_json(payload: Mapping[str, Any]) -> str:
    import json

    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _select_contract(
    source: Mapping[str, str],
    canonical_pair: Mapping[str, Any],
    alias_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    canonical_safe = _canonical_marked_read_only(source)
    if canonical_pair["api_key_present"] and canonical_pair["api_secret_present"] and canonical_safe:
        return _selected_contract(
            source="canonical",
            api_key_name=CANONICAL_API_KEY_ENV,
            api_secret_name=CANONICAL_API_SECRET_ENV,
            mode_name=CANONICAL_MODE_ENV,
            enabled_name=CANONICAL_ENABLED_ENV,
            read_only_marker_present=True,
            runtime_safety_ok=True,
        )
    for candidate in alias_candidates:
        if not candidate["api_key_present"] or not candidate["api_secret_present"]:
            continue
        alias_safe = _alias_marked_read_only(source, str(candidate["source"]))
        if alias_safe:
            return _selected_contract(
                source=str(candidate["source"]),
                api_key_name=str(candidate["api_key_env_name"]),
                api_secret_name=str(candidate["api_secret_env_name"]),
                mode_name=_selected_mode_env_name(source),
                enabled_name=_selected_enabled_env_name(source),
                read_only_marker_present=True,
                runtime_safety_ok=True,
            )
        return _selected_contract(
            source=str(candidate["source"]),
            api_key_name=str(candidate["api_key_env_name"]),
            api_secret_name=str(candidate["api_secret_env_name"]),
            mode_name=_selected_mode_env_name(source),
            enabled_name=_selected_enabled_env_name(source),
            read_only_marker_present=False,
            runtime_safety_ok=False,
        )
    return _selected_contract(
        source=None,
        api_key_name=None,
        api_secret_name=None,
        mode_name=_selected_mode_env_name(source),
        enabled_name=_selected_enabled_env_name(source),
        read_only_marker_present=False,
        runtime_safety_ok=False,
    )


def _status_for_selection(
    canonical_pair: Mapping[str, Any],
    alias_candidates: list[dict[str, Any]],
    selected: Mapping[str, Any],
) -> str:
    if selected.get("runtime_safety_ok") is True and selected.get("api_key_present") and selected.get("api_secret_present"):
        return ACCOUNT_READ_ENV_READY
    any_partial = canonical_pair.get("partial_pair") or any(candidate.get("partial_pair") for candidate in alias_candidates)
    if any_partial:
        return ACCOUNT_READ_ENV_PARTIAL
    any_pair = (
        canonical_pair.get("api_key_present")
        and canonical_pair.get("api_secret_present")
    ) or any(candidate.get("api_key_present") and candidate.get("api_secret_present") for candidate in alias_candidates)
    if any_pair:
        return ACCOUNT_READ_ENV_ALIAS_PRESENT_BUT_NOT_MARKED_READ_ONLY
    return ACCOUNT_READ_ENV_MISSING


def _blockers_for_status(
    status: str,
    selected: Mapping[str, Any],
    canonical_pair: Mapping[str, Any],
    alias_candidates: list[dict[str, Any]],
) -> list[str]:
    if status == ACCOUNT_READ_ENV_READY:
        return []
    blockers: list[str] = []
    if status == ACCOUNT_READ_ENV_MISSING:
        blockers.append("account_read_env_missing")
    if status == ACCOUNT_READ_ENV_PARTIAL:
        blockers.append("account_read_env_partial_key_secret_pair")
    if status == ACCOUNT_READ_ENV_ALIAS_PRESENT_BUT_NOT_MARKED_READ_ONLY:
        blockers.append("account_read_env_alias_present_but_not_marked_read_only")
    if selected.get("read_only_marker_present") is not True:
        blockers.append("account_read_read_only_marker_missing")
    if not (canonical_pair.get("api_key_present") and canonical_pair.get("api_secret_present")) and not any(
        candidate.get("api_key_present") and candidate.get("api_secret_present") for candidate in alias_candidates
    ):
        blockers.extend(["account_read_api_key_missing", "account_read_api_secret_missing"])
    return _dedupe(blockers)


def _pair_summary(source: Mapping[str, str], key_name: str, secret_name: str, *, source_name: str) -> dict[str, Any]:
    key_present = _presence(source, key_name)
    secret_present = _presence(source, secret_name)
    return {
        "source": source_name,
        "api_key_env_name": key_name,
        "api_secret_env_name": secret_name,
        "api_key_present": key_present,
        "api_secret_present": secret_present,
        "pair_complete": key_present and secret_present,
        "partial_pair": key_present != secret_present,
        "values_redacted": True,
        "secrets_shown": False,
    }


def _selected_contract(
    *,
    source: str | None,
    api_key_name: str | None,
    api_secret_name: str | None,
    mode_name: str | None,
    enabled_name: str | None,
    read_only_marker_present: bool,
    runtime_safety_ok: bool,
) -> dict[str, Any]:
    selected_source = "canonical" if source == "canonical" else ("alias" if source else None)
    return {
        "selected_env_source": selected_source,
        "selected_env_source_detail": source,
        "selected_api_key_env_name": api_key_name,
        "selected_api_secret_env_name": api_secret_name,
        "selected_mode_env_name": mode_name,
        "selected_enabled_env_name": enabled_name,
        "api_key_present": bool(api_key_name),
        "api_secret_present": bool(api_secret_name),
        "read_only_marker_present": bool(read_only_marker_present),
        "runtime_safety_ok": bool(runtime_safety_ok),
        "selected_env_values_redacted": True,
        "secrets_shown": False,
    }


def _canonical_marked_read_only(source: Mapping[str, str]) -> bool:
    enabled = _env_value(source, CANONICAL_ENABLED_ENV).lower()
    mode = _env_value(source, CANONICAL_MODE_ENV).lower()
    return enabled in READ_ONLY_TRUE_VALUES and mode in READ_ONLY_MODE_VALUES


def _alias_marked_read_only(source: Mapping[str, str], source_name: str) -> bool:
    if source_name == "role_specific" and _strict_runtime_flags_safe(source):
        return True
    connector_mode = _env_value(source, ENV_CONNECTOR_MODE).lower()
    live_trading = _env_value(source, ENV_LIVE_TRADING_ENABLED).lower()
    return connector_mode in READ_ONLY_MODE_VALUES and live_trading in LIVE_FALSE_VALUES


def _strict_runtime_flags_safe(source: Mapping[str, str]) -> bool:
    required = {
        ENV_CONNECTOR_MODE: READ_ONLY_MODE_VALUES,
        ENV_LIVE_TRADING_ENABLED: LIVE_FALSE_VALUES,
        ENV_BINANCE_LIVE_ENABLED: LIVE_FALSE_VALUES,
        ENV_LIVE_EXECUTION_ENABLED: LIVE_FALSE_VALUES,
        ENV_ALLOW_LIVE_ORDERS: LIVE_FALSE_VALUES,
        ENV_GLOBAL_KILL_SWITCH: {"1", "true", "yes", "on"},
    }
    return all(_env_value(source, name).lower() in allowed for name, allowed in required.items())


def _selected_mode_env_name(source: Mapping[str, str]) -> str | None:
    if _presence(source, CANONICAL_MODE_ENV):
        return CANONICAL_MODE_ENV
    if _presence(source, ENV_CONNECTOR_MODE):
        return ENV_CONNECTOR_MODE
    return None


def _selected_enabled_env_name(source: Mapping[str, str]) -> str | None:
    if _presence(source, CANONICAL_ENABLED_ENV):
        return CANONICAL_ENABLED_ENV
    if _presence(source, ENV_LIVE_TRADING_ENABLED):
        return ENV_LIVE_TRADING_ENABLED
    return None


def _runtime_env_sources(source: Mapping[str, str], *, include_systemd: bool) -> dict[str, Any]:
    process_names = [name for name in RUNTIME_SAFETY_ENV_NAMES if _presence(source, name)]
    systemd_files = _systemd_environment_files() if include_systemd else []
    candidate_paths = _dedupe([*systemd_files, "/home/josue/.config/hammer-radar/binance-readonly.env"])
    file_name_presence = {
        path: _env_file_names(path, allowed_names=DISCOVERY_ENV_NAME_ALLOWLIST)
        for path in candidate_paths
        if path
    }
    return {
        "runtime_env_sources": {
            "process_env_names_present": process_names,
            "systemd_unit_checked": bool(include_systemd),
            "env_file_name_presence": file_name_presence,
            "values_redacted": True,
        },
        "systemd_environment_files": systemd_files,
        "candidate_env_file_paths": candidate_paths,
    }


def _systemd_environment_files() -> list[str]:
    try:
        result = subprocess.run(
            ["systemctl", "show", "hammer-approval-api.service", "-p", "EnvironmentFiles"],
            text=True,
            capture_output=True,
            check=False,
            timeout=2.0,
        )
    except Exception:
        return []
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line.startswith("EnvironmentFiles="):
            continue
        raw = line.split("=", 1)[1].strip()
        for item in raw.split():
            path = item.split("(", 1)[0].strip()
            if path:
                paths.append(path)
    return _dedupe(paths)


def _allowed_runtime_env_file_paths(systemd_files: list[str] | None = None) -> list[str]:
    candidates = [*(systemd_files or []), str(KNOWN_SAFE_READONLY_ENV_FILE)]
    allowed: list[str] = []
    for candidate in candidates:
        normalized = _normalize_runtime_env_file_path(candidate, systemd_files=systemd_files)
        if normalized["allowed"]:
            allowed.append(str(normalized["path"]))
    return _dedupe(allowed)


def _normalize_runtime_env_file_path(
    path: str | Path,
    *,
    systemd_files: list[str] | None = None,
) -> dict[str, Any]:
    raw = Path(path).expanduser()
    try:
        resolved = raw.resolve(strict=False)
        allowed_dir = HAMMER_RADAR_CONFIG_DIR.resolve(strict=False)
        known = KNOWN_SAFE_READONLY_ENV_FILE.resolve(strict=False)
    except OSError:
        return {"allowed": False, "path": str(path), "status": "ENV_FILE_PATH_INVALID"}
    if allowed_dir not in [resolved, *resolved.parents]:
        return {"allowed": False, "path": str(resolved), "status": "ENV_FILE_PATH_OUTSIDE_ALLOWLIST_DIR"}
    systemd_resolved: set[Path] = set()
    discovered_files = systemd_files if systemd_files is not None else discover_systemd_env_files_for_hammer_approval_api()
    for item in discovered_files:
        try:
            item_path = Path(item).expanduser().resolve(strict=False)
        except OSError:
            continue
        systemd_resolved.add(item_path)
    if resolved != known and resolved not in systemd_resolved:
        return {"allowed": False, "path": str(resolved), "status": "ENV_FILE_PATH_NOT_DISCOVERED_OR_KNOWN_SAFE"}
    return {"allowed": True, "path": str(resolved), "status": "ENV_FILE_PATH_ALLOWED"}


def _parse_env_file_allowed_values(path: Path) -> dict[str, Any]:
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"values": {}, "ignored_names": [], "read_error": True}
    values: dict[str, str] = {}
    ignored: list[str] = []
    for row in rows:
        stripped = row.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, raw_value = stripped.split("=", 1)
        key = name.strip()
        if key not in RUNTIME_ENV_FILE_LOAD_ALLOWLIST:
            ignored.append(key)
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return {"values": values, "ignored_names": _dedupe(ignored), "read_error": False}


def _file_stat(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {"exists": False}
    return {
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "inode": stat.st_ino,
    }


def _env_file_names(path: str, *, allowed_names: list[str]) -> list[str]:
    try:
        rows = Path(path).expanduser().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    names: list[str] = []
    for row in rows:
        stripped = row.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name = stripped.split("=", 1)[0].strip()
        if name in allowed_names:
            names.append(name)
    return _dedupe(names)


def _presence(source: Mapping[str, str], name: str) -> bool:
    return bool(_env_value(source, name))


def _env_value(source: Mapping[str, str], key: str) -> str:
    return str(source.get(key) or "").strip()


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if str(key) not in {"api_key", "api_secret", "secret", "signature", "signed_url", "query"}
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
