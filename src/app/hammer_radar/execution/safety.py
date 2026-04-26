"""Safety config and live-readiness checks for Hammer Radar execution modes."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

EXECUTION_MODE_ENV_VAR = "HAMMER_RADAR_EXECUTION_MODE"
LIVE_TRADING_ENABLED_ENV_VAR = "HAMMER_RADAR_LIVE_TRADING_ENABLED"
MAX_RISK_USD_ENV_VAR = "HAMMER_RADAR_MAX_RISK_USD"
MAX_POSITION_SIZE_USD_ENV_VAR = "HAMMER_RADAR_MAX_POSITION_SIZE_USD"
MAX_OPEN_POSITIONS_ENV_VAR = "HAMMER_RADAR_MAX_OPEN_POSITIONS"
ALLOWED_SYMBOLS_ENV_VAR = "HAMMER_RADAR_ALLOWED_SYMBOLS"
REQUIRE_OPERATOR_APPROVAL_ENV_VAR = "HAMMER_RADAR_REQUIRE_OPERATOR_APPROVAL"

DEFAULT_EXECUTION_MODE = "paper"
SUPPORTED_EXECUTION_MODES = ("paper", "binance_stub")
PLANNED_LIVE_MODES = ("binance_live",)
DEFAULT_LIVE_TRADING_ENABLED = False
DEFAULT_MAX_RISK_USD = 0.0
DEFAULT_MAX_POSITION_SIZE_USD = 100.0
DEFAULT_MAX_OPEN_POSITIONS = 1
DEFAULT_ALLOWED_SYMBOLS = ("BTCUSDT",)
DEFAULT_REQUIRE_OPERATOR_APPROVAL = True


@dataclass(frozen=True, slots=True)
class ExecutionSafetyConfig:
    execution_mode: str
    live_trading_enabled: bool
    max_risk_usd: float
    max_position_size_usd: float
    max_open_positions: int
    allowed_symbols: tuple[str, ...]
    require_operator_approval: bool


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    verdict: str
    reasons: tuple[str, ...] = ()


def load_execution_safety_config() -> ExecutionSafetyConfig:
    execution_mode = os.getenv(EXECUTION_MODE_ENV_VAR, DEFAULT_EXECUTION_MODE).strip().lower()
    if execution_mode not in SUPPORTED_EXECUTION_MODES and execution_mode not in PLANNED_LIVE_MODES:
        raise ValueError(f"Unsupported execution mode: {execution_mode}")

    live_trading_enabled = _parse_bool(
        os.getenv(LIVE_TRADING_ENABLED_ENV_VAR),
        default=DEFAULT_LIVE_TRADING_ENABLED,
    )
    max_risk_usd = _parse_float(os.getenv(MAX_RISK_USD_ENV_VAR), default=DEFAULT_MAX_RISK_USD)
    max_position_size_usd = _parse_float(
        os.getenv(MAX_POSITION_SIZE_USD_ENV_VAR),
        default=DEFAULT_MAX_POSITION_SIZE_USD,
    )
    max_open_positions = _parse_int(
        os.getenv(MAX_OPEN_POSITIONS_ENV_VAR),
        default=DEFAULT_MAX_OPEN_POSITIONS,
    )
    allowed_symbols = _parse_allowed_symbols(
        os.getenv(ALLOWED_SYMBOLS_ENV_VAR),
        default=DEFAULT_ALLOWED_SYMBOLS,
    )
    require_operator_approval = _parse_bool(
        os.getenv(REQUIRE_OPERATOR_APPROVAL_ENV_VAR),
        default=DEFAULT_REQUIRE_OPERATOR_APPROVAL,
    )

    config = ExecutionSafetyConfig(
        execution_mode=execution_mode,
        live_trading_enabled=live_trading_enabled,
        max_risk_usd=max_risk_usd,
        max_position_size_usd=max_position_size_usd,
        max_open_positions=max_open_positions,
        allowed_symbols=allowed_symbols,
        require_operator_approval=require_operator_approval,
    )
    _validate_execution_safety_config(config)
    return config


def evaluate_live_readiness(config: ExecutionSafetyConfig) -> ReadinessResult:
    if config.execution_mode == "paper":
        return ReadinessResult(verdict="READY_FOR_PAPER")
    if config.execution_mode == "binance_stub":
        return ReadinessResult(verdict="READY_FOR_STUB_ONLY")

    reasons = ["Live trading capability is not implemented in this phase."]
    if not config.live_trading_enabled:
        reasons.append("Live trading is not explicitly enabled.")
    if config.max_risk_usd <= 0.0:
        reasons.append("Max risk USD must be greater than zero for any future live mode.")
    if not config.require_operator_approval:
        reasons.append("Operator approval must remain required.")
    return ReadinessResult(verdict="NOT_READY", reasons=tuple(reasons))


def build_safety_check_text() -> str:
    config = load_execution_safety_config()
    readiness = evaluate_live_readiness(config)
    lines = [
        "HAMMER RADAR SAFETY CHECK",
        f"execution_mode: {config.execution_mode}",
        f"live_trading_enabled: {'true' if config.live_trading_enabled else 'false'}",
        f"allowed_symbols: {', '.join(config.allowed_symbols)}",
        f"max_position_size_usd: {config.max_position_size_usd:.2f}",
        f"max_open_positions: {config.max_open_positions}",
        f"require_operator_approval: {'true' if config.require_operator_approval else 'false'}",
        f"final_readiness_verdict: {readiness.verdict}",
    ]
    for reason in readiness.reasons:
        lines.append(f"reason: {reason}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.execution.safety")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check")
    args = parser.parse_args()
    if args.command == "check":
        print(build_safety_check_text())
        return 0
    parser.error(f"unsupported command: {args.command}")
    return 2


def _validate_execution_safety_config(config: ExecutionSafetyConfig) -> None:
    if config.max_risk_usd < 0.0:
        raise ValueError("max_risk_usd must be zero or greater")
    if config.max_position_size_usd <= 0.0:
        raise ValueError("max_position_size_usd must be greater than zero")
    if config.max_position_size_usd > DEFAULT_MAX_POSITION_SIZE_USD:
        raise ValueError("max_position_size_usd exceeds the current safe limit")
    if config.max_open_positions < 0:
        raise ValueError("max_open_positions must be zero or greater")
    if config.max_open_positions > DEFAULT_MAX_OPEN_POSITIONS:
        raise ValueError("max_open_positions exceeds the current safe limit")
    if config.allowed_symbols != DEFAULT_ALLOWED_SYMBOLS:
        raise ValueError("allowed_symbols must remain restricted to BTCUSDT in this phase")
    if config.execution_mode in SUPPORTED_EXECUTION_MODES and config.live_trading_enabled:
        raise ValueError("live_trading_enabled must remain false for current supported modes")
    if config.execution_mode in PLANNED_LIVE_MODES:
        if not config.live_trading_enabled:
            raise ValueError("planned live mode requires explicit live_trading_enabled=true")
        if config.max_risk_usd <= 0.0:
            raise ValueError("planned live mode requires max_risk_usd > 0")
        if not config.require_operator_approval:
            raise ValueError("planned live mode requires operator approval")


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def _parse_float(value: str | None, *, default: float) -> float:
    if value is None or value == "":
        return default
    return float(value)


def _parse_int(value: str | None, *, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _parse_allowed_symbols(value: str | None, *, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None or value == "":
        return default
    symbols = tuple(part.strip().upper() for part in value.split(",") if part.strip())
    if not symbols:
        raise ValueError("allowed_symbols must not be empty")
    return symbols


if __name__ == "__main__":
    raise SystemExit(main())
