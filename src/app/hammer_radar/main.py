"""Runtime loop for the Hammer Radar v1 pipeline."""

from __future__ import annotations

import json
import time

from src.app.hammer_radar.hammer_detector import annotate_hammers
from src.app.hammer_radar.market_reader import MarketReader
from src.app.hammer_radar.signal_engine import attach_bias, compute_bias_direction, extract_signal

TIMEFRAMES = (
    ("13min", "13m"),
    ("55min", "55m"),
)


def run(sleep_seconds: float = 3.0) -> None:
    """Start the reader and continuously print new hammer signals."""
    print("Hammer Radar started")
    reader = MarketReader()
    seen_signal_keys = set()

    try:
        reader.start()
        print("Reader started")
        print("Waiting for signals...")

        while True:
            try:
                dataframe_1m = reader.get_dataframe()
                if dataframe_1m.empty:
                    print("Waiting for market data...")
                else:
                    bias_direction = compute_bias_direction(reader.get_resampled("4h"))
                    for resample_rule, timeframe_label in TIMEFRAMES:
                        resampled = reader.get_resampled(resample_rule)
                        annotated = annotate_hammers(resampled)
                        signal = extract_signal(annotated, "BTCUSDT", timeframe=timeframe_label)

                        if not signal:
                            continue
                        signal = attach_bias(signal, bias_direction=bias_direction, bias_timeframe="4H")

                        signal_key = (
                            signal.get("timeframe"),
                            signal.get("timestamp"),
                            signal.get("direction"),
                        )
                        if signal_key in seen_signal_keys:
                            continue

                        print(_format_operator_brief(signal))
                        print(json.dumps(signal, indent=2, sort_keys=True))
                        seen_signal_keys.add(signal_key)
            except Exception as error:
                print(f"Hammer Radar loop error: {error}")

            time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        print("Stopping Hammer Radar...")
    finally:
        reader.stop()
        print("Hammer Radar stopped")


def _format_operator_brief(signal: dict) -> str:
    """Return a concise terminal brief for a detected hammer signal."""
    direction = signal["direction"]
    invalidation_side = "below" if direction == "long" else "above"
    golden_pocket_low = min(signal["fib_618"], signal["fib_650"])
    golden_pocket_high = max(signal["fib_618"], signal["fib_650"])
    if signal["bias_direction"] == "neutral":
        bias_status = "neutral"
    elif signal["bias_aligned"]:
        bias_status = "aligned"
    else:
        bias_status = "counter-bias"
    return (
        f"HAMMER SIGNAL [{signal['timeframe']}] {signal['symbol']} {direction.upper()} | "
        f"strength={signal['hammer_strength']:.2f} | "
        f"{signal['bias_timeframe']} bias={signal['bias_direction']} | "
        f"bias_status={bias_status} | "
        f"hammer={signal['hammer_low']:.2f}-{signal['hammer_high']:.2f} | "
        f"golden_pocket={golden_pocket_low:.2f}-{golden_pocket_high:.2f} | "
        f"invalidation={invalidation_side} {signal['invalidation']:.2f}"
    )

if __name__ == "__main__":
    run()
