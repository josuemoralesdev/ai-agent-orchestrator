"""Runtime loop for the Hammer Radar v1 pipeline."""

from __future__ import annotations

import time

from src.app.hammer_radar.hammer_detector import annotate_hammers
from src.app.hammer_radar.market_reader import MarketReader
from src.app.hammer_radar.signal_engine import extract_signal


def run(sleep_seconds: float = 3.0) -> None:
    """Start the reader and continuously print new hammer signals."""
    print("Hammer Radar started")
    reader = MarketReader()
    last_signal_key = None

    try:
        reader.start()
        print("Reader started")
        print("Waiting for signals...")

        while True:
            try:
                dataframe = reader.get_dataframe()
                annotated = annotate_hammers(dataframe)
                signal = extract_signal(annotated, "BTCUSDT")

                if signal:
                    signal_key = (signal.get("timestamp"), signal.get("direction"))
                    if signal_key != last_signal_key:
                        print("HAMMER SIGNAL DETECTED")
                        print(signal)
                        last_signal_key = signal_key
                elif dataframe.empty:
                    print("Waiting for market data...")
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
