"""Strategy timeframe and filter configuration for Hammer Radar."""

from __future__ import annotations

import os
from dataclasses import dataclass

from src.app.hammer_radar.operator.evaluator import DEFAULT_ENTRY_MODES

TIMEFRAME_CONFIGS = (
    ("13min", "13m"),
    ("55min", "55m"),
    ("666min", "666m"),
    ("4h", "4H"),
    ("13h", "13H"),
    ("13D", "13D"),
)
SUPPORTED_TIMEFRAME_LABELS = tuple(label for _rule, label in TIMEFRAME_CONFIGS)
TIMEFRAME_MINUTES = {
    "13m": 13,
    "55m": 55,
    "666m": 666,
    "4H": 240,
    "13H": 780,
    "13D": 18720,
}
DEFAULT_MINIMUM_HAMMER_STRENGTH = 85.0
DEFAULT_REQUIRE_BIAS_ALIGNMENT = True
DEFAULT_MAX_RECENT_SAME_DIRECTION_GAP = 2
DEFAULT_PAPER_ENABLED = True
DEFAULT_TAKE_PROFIT_R_MULTIPLE = 2.0
DEFAULT_MAX_HOLD_CANDLES = 3
DEFAULT_EXIT_ON_STOP = True
DEFAULT_EXIT_ON_TAKE_PROFIT = True
DEFAULT_EXIT_ON_MAX_HOLD = True


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    enabled_timeframes: tuple[str, ...]
    minimum_hammer_strength: float
    require_bias_alignment: bool
    allowed_entry_modes: tuple[str, ...]
    blocked_entry_modes: tuple[str, ...]
    max_recent_same_direction_gap: int
    paper_enabled: bool
    take_profit_r_multiple: float
    max_hold_candles: int
    exit_on_stop: bool
    exit_on_take_profit: bool
    exit_on_max_hold: bool


def load_strategy_config() -> StrategyConfig:
    enabled_timeframes = _parse_labels(
        os.getenv("HAMMER_RADAR_ENABLED_TIMEFRAMES"),
        default=SUPPORTED_TIMEFRAME_LABELS,
        supported=SUPPORTED_TIMEFRAME_LABELS,
        field_name="enabled_timeframes",
    )
    allowed_entry_modes = _parse_labels(
        os.getenv("HAMMER_RADAR_ALLOWED_ENTRY_MODES"),
        default=tuple(DEFAULT_ENTRY_MODES),
        supported=tuple(DEFAULT_ENTRY_MODES),
        field_name="allowed_entry_modes",
    )
    blocked_entry_modes = _parse_labels(
        os.getenv("HAMMER_RADAR_BLOCKED_ENTRY_MODES"),
        default=(),
        supported=tuple(DEFAULT_ENTRY_MODES),
        field_name="blocked_entry_modes",
    )
    config = StrategyConfig(
        enabled_timeframes=enabled_timeframes,
        minimum_hammer_strength=_parse_float(
            os.getenv("HAMMER_RADAR_MINIMUM_HAMMER_STRENGTH"),
            default=DEFAULT_MINIMUM_HAMMER_STRENGTH,
        ),
        require_bias_alignment=_parse_bool(
            os.getenv("HAMMER_RADAR_REQUIRE_BIAS_ALIGNMENT"),
            default=DEFAULT_REQUIRE_BIAS_ALIGNMENT,
        ),
        allowed_entry_modes=allowed_entry_modes,
        blocked_entry_modes=blocked_entry_modes,
        max_recent_same_direction_gap=_parse_int(
            os.getenv("HAMMER_RADAR_MAX_RECENT_SAME_DIRECTION_GAP"),
            default=DEFAULT_MAX_RECENT_SAME_DIRECTION_GAP,
        ),
        paper_enabled=_parse_bool(
            os.getenv("HAMMER_RADAR_PAPER_ENABLED"),
            default=DEFAULT_PAPER_ENABLED,
        ),
        take_profit_r_multiple=_parse_float(
            os.getenv("HAMMER_RADAR_TAKE_PROFIT_R_MULTIPLE"),
            default=DEFAULT_TAKE_PROFIT_R_MULTIPLE,
        ),
        max_hold_candles=_parse_int(
            os.getenv("HAMMER_RADAR_MAX_HOLD_CANDLES"),
            default=DEFAULT_MAX_HOLD_CANDLES,
        ),
        exit_on_stop=_parse_bool(
            os.getenv("HAMMER_RADAR_EXIT_ON_STOP"),
            default=DEFAULT_EXIT_ON_STOP,
        ),
        exit_on_take_profit=_parse_bool(
            os.getenv("HAMMER_RADAR_EXIT_ON_TAKE_PROFIT"),
            default=DEFAULT_EXIT_ON_TAKE_PROFIT,
        ),
        exit_on_max_hold=_parse_bool(
            os.getenv("HAMMER_RADAR_EXIT_ON_MAX_HOLD"),
            default=DEFAULT_EXIT_ON_MAX_HOLD,
        ),
    )
    _validate_strategy_config(config)
    return config


def is_timeframe_enabled(timeframe: str, config: StrategyConfig | None = None) -> bool:
    strategy_config = config or load_strategy_config()
    return timeframe in strategy_config.enabled_timeframes


def is_entry_mode_allowed(entry_mode: str, config: StrategyConfig | None = None) -> bool:
    strategy_config = config or load_strategy_config()
    return entry_mode in strategy_config.allowed_entry_modes and entry_mode not in strategy_config.blocked_entry_modes


def filter_summary_rows_for_strategy(rows: list[dict], config: StrategyConfig | None = None) -> list[dict]:
    strategy_config = config or load_strategy_config()
    filtered: list[dict] = []
    for row in rows:
        if row.get("timeframe") not in strategy_config.enabled_timeframes:
            continue
        if strategy_config.require_bias_alignment and not row.get("bias_aligned"):
            continue
        if not _strength_band_meets_minimum(str(row.get("strength_band", "")), strategy_config.minimum_hammer_strength):
            continue
        if not is_entry_mode_allowed(str(row.get("entry_mode", "")), strategy_config):
            continue
        filtered.append(row)
    return filtered


def _validate_strategy_config(config: StrategyConfig) -> None:
    if not config.enabled_timeframes:
        raise ValueError("enabled_timeframes must not be empty")
    if config.minimum_hammer_strength < 0.0 or config.minimum_hammer_strength > 100.0:
        raise ValueError("minimum_hammer_strength must be between 0 and 100")
    if config.max_recent_same_direction_gap < 0:
        raise ValueError("max_recent_same_direction_gap must be zero or greater")
    if config.take_profit_r_multiple <= 0.0:
        raise ValueError("take_profit_r_multiple must be greater than zero")
    if config.max_hold_candles < 0:
        raise ValueError("max_hold_candles must be zero or greater")
    unknown_allowed = set(config.allowed_entry_modes) - set(DEFAULT_ENTRY_MODES)
    if unknown_allowed:
        raise ValueError(f"allowed_entry_modes contains unsupported values: {sorted(unknown_allowed)}")
    unknown_blocked = set(config.blocked_entry_modes) - set(DEFAULT_ENTRY_MODES)
    if unknown_blocked:
        raise ValueError(f"blocked_entry_modes contains unsupported values: {sorted(unknown_blocked)}")
    unknown_timeframes = set(config.enabled_timeframes) - set(SUPPORTED_TIMEFRAME_LABELS)
    if unknown_timeframes:
        raise ValueError(f"enabled_timeframes contains unsupported values: {sorted(unknown_timeframes)}")


def _parse_labels(
    raw: str | None,
    *,
    default: tuple[str, ...],
    supported: tuple[str, ...],
    field_name: str,
) -> tuple[str, ...]:
    if raw is None or raw == "":
        return default
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    unsupported = set(values) - set(supported)
    if unsupported:
        raise ValueError(f"{field_name} contains unsupported values: {sorted(unsupported)}")
    return values


def _parse_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"invalid boolean value: {raw}")


def _parse_float(raw: str | None, *, default: float) -> float:
    if raw is None or raw == "":
        return default
    return float(raw)


def _parse_int(raw: str | None, *, default: int) -> int:
    if raw is None or raw == "":
        return default
    return int(raw)


def _strength_band_meets_minimum(strength_band: str, minimum: float) -> bool:
    if not strength_band:
        return False
    if strength_band.startswith("<"):
        return float(strength_band[1:]) >= minimum
    if strength_band.startswith(">"):
        return float(strength_band[1:]) >= minimum
    if "-" in strength_band:
        lower_text, _upper_text = strength_band.split("-", 1)
        return float(lower_text) >= minimum
    return False
