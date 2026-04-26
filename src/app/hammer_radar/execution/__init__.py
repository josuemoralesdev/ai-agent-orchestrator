"""Execution adapter boundary selection for Hammer Radar."""

from __future__ import annotations

from src.app.hammer_radar.execution.base import AccountSnapshot, ExecutionAdapter, OrderResult
from src.app.hammer_radar.execution.binance_stub import BinanceStubAdapter
from src.app.hammer_radar.execution.paper import PaperExecutionAdapter

EXECUTION_MODE_ENV_VAR = "HAMMER_RADAR_EXECUTION_MODE"
DEFAULT_EXECUTION_MODE = "paper"
SUPPORTED_EXECUTION_MODES = ("paper", "binance_stub")


def get_execution_mode() -> str:
    from src.app.hammer_radar.execution.safety import load_execution_safety_config

    return load_execution_safety_config().execution_mode


def get_execution_adapter(mode: str | None = None) -> ExecutionAdapter:
    selected_mode = DEFAULT_EXECUTION_MODE if mode is None else mode.strip().lower()
    if selected_mode == "paper":
        return PaperExecutionAdapter()
    if selected_mode == "binance_stub":
        return BinanceStubAdapter()
    raise ValueError(
        f"Unsupported execution mode: {selected_mode}. Supported modes: {', '.join(SUPPORTED_EXECUTION_MODES)}"
    )


__all__ = [
    "AccountSnapshot",
    "DEFAULT_EXECUTION_MODE",
    "EXECUTION_MODE_ENV_VAR",
    "ExecutionAdapter",
    "OrderResult",
    "SUPPORTED_EXECUTION_MODES",
    "get_execution_adapter",
    "get_execution_mode",
]
