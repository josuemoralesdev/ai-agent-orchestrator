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
) -> dict[str, Any]:
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
