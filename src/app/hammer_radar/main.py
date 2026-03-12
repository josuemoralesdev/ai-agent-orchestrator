"""Runtime loop for the Hammer Radar v1 pipeline."""

from __future__ import annotations

import time

from src.app.hammer_radar.hammer_detector import annotate_hammers
from src.app.hammer_radar.market_reader import MarketReader
from src.app.hammer_radar.signal_engine import extract_signal

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
                    for resample_rule, timeframe_label in TIMEFRAMES:
                        resampled = reader.get_resampled(resample_rule)
                        annotated = annotate_hammers(resampled)
                        signal = extract_signal(annotated, "BTCUSDT", timeframe=timeframe_label)

                        if not signal:
                            continue

                        signal_key = (
                            signal.get("timeframe"),
                            signal.get("timestamp"),
                            signal.get("direction"),
                        )
                        if signal_key in seen_signal_keys:
                            continue

                        print(f"HAMMER SIGNAL DETECTED [{timeframe_label}]")
                        print(signal)
                        seen_signal_keys.add(signal_key)
            except Exception as error:
                print(f"Hammer Radar loop error: {error}")

            time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        print("Stopping Hammer Radar...")
    finally:
        reader.stop()
        print("Hammer Radar stopped")

if __name__ == "__main__":
    run()
