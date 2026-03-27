"""Summary statistics for archived Hammer Radar setups."""

from __future__ import annotations

from collections import defaultdict

from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord

STRENGTH_BANDS = (
    (60, 69),
    (70, 79),
    (80, 89),
    (90, 100),
)


def build_setup_summary(
    signals: list[SignalRecord],
    outcomes: list[OutcomeRecord],
    tradable_only: bool = False,
) -> list[dict]:
    signal_by_id = {signal.signal_id: signal for signal in signals}
    buckets: dict[tuple[str, str, bool, str], dict] = defaultdict(_new_bucket)

    for outcome in outcomes:
        signal = signal_by_id.get(outcome.signal_id)
        if signal is None:
            continue
        if tradable_only and not signal.tradable:
            continue

        bucket_key = (
            signal.timeframe,
            signal.direction,
            signal.bias_aligned,
            _strength_band(signal.hammer_strength),
            outcome.entry_mode,
        )
        bucket = buckets[bucket_key]
        bucket["timeframe"] = signal.timeframe
        bucket["direction"] = signal.direction
        bucket["bias_aligned"] = signal.bias_aligned
        bucket["strength_band"] = _strength_band(signal.hammer_strength)
        bucket["entry_mode"] = outcome.entry_mode
        bucket["samples"] += 1

        if outcome.fill_status == "filled":
            bucket["fills"] += 1
            if outcome.pnl_pct > 0.0:
                bucket["wins"] += 1
            else:
                bucket["losses"] += 1
            if outcome.stop_hit:
                bucket["stops"] += 1
            bucket["pnl_total"] += outcome.pnl_pct
            bucket["mae_total"] += outcome.mae_pct
            bucket["mfe_total"] += outcome.mfe_pct

    rows: list[dict] = []
    for bucket in buckets.values():
        fills = bucket["fills"]
        samples = bucket["samples"]
        rows.append(
            {
                "timeframe": bucket["timeframe"],
                "direction": bucket["direction"],
                "bias_aligned": bucket["bias_aligned"],
                "strength_band": bucket["strength_band"],
                "entry_mode": bucket["entry_mode"],
                "samples": samples,
                "fills": fills,
                "fill_rate": round((fills / samples) * 100.0, 2) if samples else 0.0,
                "wins": bucket["wins"],
                "losses": bucket["losses"],
                "stops": bucket["stops"],
                "win_rate_on_filled": round((bucket["wins"] / fills) * 100.0, 2) if fills else 0.0,
                "avg_pnl_pct": round(bucket["pnl_total"] / fills, 4) if fills else 0.0,
                "avg_mae_pct": round(bucket["mae_total"] / fills, 4) if fills else 0.0,
                "avg_mfe_pct": round(bucket["mfe_total"] / fills, 4) if fills else 0.0,
            }
        )

    return sorted(
        rows,
        key=lambda row: (
            -row["samples"],
            -row["win_rate_on_filled"],
            -row["avg_pnl_pct"],
        ),
    )


def _strength_band(strength: float) -> str:
    rounded = int(strength)
    for lower, upper in STRENGTH_BANDS:
        if lower <= rounded <= upper:
            return f"{lower}-{upper}"
    if rounded < STRENGTH_BANDS[0][0]:
        return f"<{STRENGTH_BANDS[0][0]}"
    return f">{STRENGTH_BANDS[-1][1]}"


def _new_bucket() -> dict:
    return {
        "timeframe": "",
        "direction": "",
        "bias_aligned": False,
        "strength_band": "",
        "entry_mode": "",
        "samples": 0,
        "fills": 0,
        "wins": 0,
        "losses": 0,
        "stops": 0,
        "pnl_total": 0.0,
        "mae_total": 0.0,
        "mfe_total": 0.0,
    }
