"""Minimal Binance Futures BTCUSDT market reader for Hammer Radar."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Iterable

import requests

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - depends on runtime environment
    pd = None

try:
    import websocket
except ModuleNotFoundError:  # pragma: no cover - depends on runtime environment
    websocket = None


class MarketReader:
    """Read closed BTCUSDT perpetual 1m candles into a rolling dataframe buffer."""

    symbol = "BTCUSDT"
    interval = "1m"
    rest_url = "https://fapi.binance.com/fapi/v1/klines"
    websocket_url = "wss://fstream.binance.com/ws/btcusdt@kline_1m"
    dataframe_columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
    ]

    def __init__(
        self,
        buffer_size: int = 2000,
        snapshot_limit: int = 500,
        request_timeout: float = 10.0,
        poll_interval_seconds: float = 5.0,
        websocket_stale_seconds: float = 90.0,
    ) -> None:
        self.buffer_size = buffer_size
        self.snapshot_limit = min(snapshot_limit, buffer_size)
        self.request_timeout = request_timeout
        self.poll_interval_seconds = poll_interval_seconds
        self.websocket_stale_seconds = websocket_stale_seconds

        self._lock = threading.Lock()
        self._session = requests.Session()
        self._dataframe = None
        self._stop_event = threading.Event()
        self._started = False
        self._ws_app: Any = None
        self._ws_thread: threading.Thread | None = None
        self._poll_thread: threading.Thread | None = None
        self._last_websocket_message_at = 0.0

    def start(self) -> None:
        """Seed recent candles and start background readers."""
        if self._started:
            return

        self._started = True
        self._fetch_snapshot(limit=self.snapshot_limit)

        if websocket is not None:
            self._ws_thread = threading.Thread(
                target=self._run_websocket_loop,
                name="hammer-radar-ws",
                daemon=True,
            )
            self._ws_thread.start()

        self._poll_thread = threading.Thread(
            target=self._run_poll_loop,
            name="hammer-radar-poll",
            daemon=True,
        )
        self._poll_thread.start()

    def stop(self) -> None:
        """Stop background readers."""
        self._stop_event.set()
        if self._ws_app is not None:
            try:
                self._ws_app.close()
            except Exception:
                pass

    def get_dataframe(self):
        """Return a copy of the buffered 1m candle dataframe."""
        self._require_pandas()
        self._ensure_dataframe()
        with self._lock:
            return self._dataframe.copy()

    def get_resampled(self, rule: str):
        """Return a resampled OHLCV dataframe for a pandas offset rule."""
        self._require_pandas()
        frame = self.get_dataframe()
        if frame.empty:
            return frame

        working = frame.set_index("open_time")
        aggregated = (
            working.resample(rule)
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                    "close_time": "max",
                }
            )
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
        )
        if aggregated.empty:
            return self._new_dataframe()

        complete = self._drop_incomplete_resampled(aggregated, rule, frame["close_time"].max())
        return complete[self.dataframe_columns].reset_index(drop=True)

    def _run_websocket_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._ws_app = websocket.WebSocketApp(
                    self.websocket_url,
                    on_message=self._on_websocket_message,
                    on_error=self._on_websocket_error,
                    on_close=self._on_websocket_close,
                )
                self._ws_app.run_forever(ping_interval=20, ping_timeout=10)
            except Exception:
                pass

            if self._stop_event.is_set():
                return
            time.sleep(3)

    def _run_poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._should_poll():
                    self._poll_latest()
            except Exception:
                pass
            self._stop_event.wait(self.poll_interval_seconds)

    def _should_poll(self) -> bool:
        if websocket is None or self._ws_thread is None:
            return True
        if not self._ws_thread.is_alive():
            return True
        return (time.time() - self._last_websocket_message_at) > self.websocket_stale_seconds

    def _on_websocket_message(self, _ws: Any, message: str) -> None:
        payload = json.loads(message)
        kline = payload.get("k")
        if not kline or not kline.get("x"):
            return

        row = {
            "open_time": int(kline["t"]),
            "open": kline["o"],
            "high": kline["h"],
            "low": kline["l"],
            "close": kline["c"],
            "volume": kline["v"],
            "close_time": int(kline["T"]),
        }
        self._last_websocket_message_at = time.time()
        self._ingest_rows([row])

    def _on_websocket_error(self, _ws: Any, _error: Any) -> None:
        self._last_websocket_message_at = 0.0

    def _on_websocket_close(self, _ws: Any, _status_code: Any, _message: Any) -> None:
        self._last_websocket_message_at = 0.0

    def _poll_latest(self) -> None:
        last_open_time = self._latest_open_time_ms()
        params: dict[str, Any] = {
            "symbol": self.symbol,
            "interval": self.interval,
            "limit": 3,
        }
        if last_open_time is not None:
            params["startTime"] = last_open_time + 60_000
            params["limit"] = 100

        response = self._session.get(
            self.rest_url,
            params=params,
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        self._ingest_rest_klines(response.json())

    def _fetch_snapshot(self, limit: int) -> None:
        response = self._session.get(
            self.rest_url,
            params={
                "symbol": self.symbol,
                "interval": self.interval,
                "limit": limit,
            },
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        self._ingest_rest_klines(response.json())

    def _ingest_rest_klines(self, klines: Iterable[list[Any]]) -> None:
        rows = []
        now_ms = int(time.time() * 1000)
        for item in klines:
            if len(item) < 7:
                continue
            close_time = int(item[6])
            if close_time >= now_ms:
                continue
            rows.append(
                {
                    "open_time": int(item[0]),
                    "open": item[1],
                    "high": item[2],
                    "low": item[3],
                    "close": item[4],
                    "volume": item[5],
                    "close_time": close_time,
                }
            )
        self._ingest_rows(rows)

    def _ingest_rows(self, rows: Iterable[dict[str, Any]]) -> None:
        self._require_pandas()
        rows = list(rows)
        if not rows:
            return

        self._ensure_dataframe()
        incoming = pd.DataFrame(rows)
        incoming["open_time"] = pd.to_datetime(incoming["open_time"], unit="ms", utc=True)
        incoming["close_time"] = pd.to_datetime(incoming["close_time"], unit="ms", utc=True)
        for column in ("open", "high", "low", "close", "volume"):
            incoming[column] = incoming[column].astype(float)

        incoming = incoming[self.dataframe_columns]
        incoming = incoming.drop_duplicates(subset=["open_time"], keep="last")
        incoming = incoming.sort_values("open_time")

        with self._lock:
            combined = pd.concat([self._dataframe, incoming], ignore_index=True)
            combined = combined.drop_duplicates(subset=["open_time"], keep="last")
            combined = combined.sort_values("open_time").tail(self.buffer_size)
            self._dataframe = combined.reset_index(drop=True)

    def _latest_open_time_ms(self) -> int | None:
        self._require_pandas()
        self._ensure_dataframe()
        with self._lock:
            if self._dataframe.empty:
                return None
            latest = self._dataframe["open_time"].iloc[-1]
        return int(latest.timestamp() * 1000)

    def _drop_incomplete_resampled(self, frame, rule: str, latest_close_time):
        if frame.empty:
            return frame

        offset = pd.tseries.frequencies.to_offset(rule)
        last_open_time = frame["open_time"].iloc[-1]
        period_end = last_open_time + offset
        if latest_close_time < (period_end - pd.Timedelta(milliseconds=1)):
            return frame.iloc[:-1].reset_index(drop=True)
        return frame

    def _new_dataframe(self):
        self._require_pandas()
        frame = pd.DataFrame(columns=self.dataframe_columns)
        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = frame[column].astype(float)
        for column in ("open_time", "close_time"):
            frame[column] = pd.to_datetime(frame[column], utc=True)
        return frame

    def _ensure_dataframe(self) -> None:
        if self._dataframe is None:
            self._dataframe = self._new_dataframe()

    @staticmethod
    def _require_pandas() -> None:
        if pd is None:
            raise RuntimeError("pandas is required for MarketReader")
