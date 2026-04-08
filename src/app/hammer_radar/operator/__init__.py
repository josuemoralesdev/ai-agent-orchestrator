"""Hammer Radar operator-layer exports."""

from src.app.hammer_radar.operator.archive import (
    append_outcome,
    append_signal,
    load_evaluated_outcome_keys,
    load_evaluated_signal_ids,
    load_outcomes,
    load_signals,
)
from src.app.hammer_radar.operator.evaluator import (
    DEFAULT_ENTRY_MODES,
    evaluate_signal_all_entry_modes,
    evaluate_signal_on_next_candle,
)
from src.app.hammer_radar.operator.gate import decide_trade_candidate
from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord
from src.app.hammer_radar.operator.report import (
    format_outcome_line,
    format_signal_operator_line,
    format_stats_summary,
)
from src.app.hammer_radar.operator.stats import (
    build_setup_summary,
    price_vs_ema_band,
    trend_strength_band,
)

__all__ = [
    "OutcomeRecord",
    "SignalRecord",
    "append_outcome",
    "append_signal",
    "build_setup_summary",
    "decide_trade_candidate",
    "DEFAULT_ENTRY_MODES",
    "evaluate_signal_all_entry_modes",
    "evaluate_signal_on_next_candle",
    "format_outcome_line",
    "format_signal_operator_line",
    "format_stats_summary",
    "load_evaluated_outcome_keys",
    "load_evaluated_signal_ids",
    "load_outcomes",
    "load_signals",
    "price_vs_ema_band",
    "trend_strength_band",
]
