"""Public market intelligence for the Hammer Radar watchlist.

R32 uses public/read-only market data only. It never reads credentials, places
orders, or changes BTCUSDT-only live readiness.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.alt_watchlist import build_watchlist, build_watchlist_summary
from src.app.hammer_radar.operator.archive import get_log_dir

LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False
SNAPSHOTS_FILENAME = "market_intelligence_snapshots.ndjson"
SOURCE = "market_intelligence"
KEY_ROTATION_PAIR = "ETHBTC"
WARNING = "market intelligence is public/read-only and paper/watch-only"

FUTURES_TICKER_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol}"
SPOT_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
FUTURES_EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
SPOT_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo?symbol={symbol}"

STATIC_RULES: dict[str, dict[str, float]] = {
    "BTCUSDT": {"min_notional_usd": 5.0, "tick_size": 0.1, "step_size": 0.001},
    "ETHUSDT": {"min_notional_usd": 5.0, "tick_size": 0.01, "step_size": 0.001},
    "ETHBTC": {"min_notional_usd": 0.0001, "tick_size": 0.000001, "step_size": 0.0001},
}


def fetch_json(url: str, *, timeout: float = 8.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "hammer-radar-market-intelligence"}, method="GET")
    with urllib.request.urlopen(request, timeout=min(timeout, 8.0)) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body) if body else {}
    return parsed if isinstance(parsed, dict) else {"data": parsed}


def fetch_ticker(symbol: str, *, timeout: float = 8.0) -> dict[str, Any]:
    url = SPOT_TICKER_URL.format(symbol=symbol) if symbol == KEY_ROTATION_PAIR else FUTURES_TICKER_URL.format(symbol=symbol)
    return fetch_json(url, timeout=timeout)


def build_market_intelligence_summary(
    *,
    use_network: bool = False,
    write: bool = False,
    limit: int = 20,
    log_dir: str | Path | None = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    symbols = _symbol_intelligence(use_network=use_network, log_dir=resolved_log_dir, timeout=timeout)
    symbols.sort(key=lambda record: (-int(record["market_intelligence_score"]), record["symbol"]))
    if limit > 0:
        symbols = symbols[:limit]
    for rank, record in enumerate(symbols, start=1):
        record["rank"] = rank
    rotation = evaluate_ethbtc_rotation_from_symbols(symbols, use_network=use_network, log_dir=resolved_log_dir, timeout=timeout)
    status = _summary_status(symbols, network_used=use_network)
    snapshot = {
        "snapshot_id": _snapshot_id(),
        "created_at": datetime.now(UTC).isoformat(),
        "source": SOURCE,
        "network_used": bool(use_network),
        "market_data_status": status,
        "symbols_count": len(symbols),
        "key_rotation_pair": KEY_ROTATION_PAIR,
        "btc_live_only": True,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "top_ranked_symbols": [record["symbol"] for record in symbols[:5]],
        "ethbtc_rotation_state": rotation["rotation_state"],
        "warning": WARNING,
        "symbols": symbols,
    }
    if write:
        append_market_snapshot(snapshot, log_dir=resolved_log_dir)
    snapshot["write"] = bool(write)
    return snapshot


def build_market_rankings(
    *,
    use_network: bool = False,
    category: str | None = None,
    limit: int = 20,
    log_dir: str | Path | None = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
    records = _symbol_intelligence(use_network=use_network, log_dir=get_log_dir(log_dir, use_env=True), timeout=timeout)
    if category is not None:
        records = [record for record in records if record["category"] == category]
    records.sort(key=lambda record: (-int(record["market_intelligence_score"]), record["symbol"]))
    if limit > 0:
        records = records[:limit]
    for rank, record in enumerate(records, start=1):
        record["rank"] = rank
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "network_used": bool(use_network),
        "market_data_status": _summary_status(records, network_used=use_network),
        "ranked_symbols": records,
        "btc_live_only": True,
        "warning": WARNING,
    }


def evaluate_ethbtc_rotation(
    *,
    use_network: bool = False,
    log_dir: str | Path | None = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
    symbols = _symbol_intelligence(use_network=use_network, log_dir=get_log_dir(log_dir, use_env=True), timeout=timeout)
    return evaluate_ethbtc_rotation_from_symbols(symbols, use_network=use_network, log_dir=log_dir, timeout=timeout)


def evaluate_ethbtc_rotation_from_symbols(
    symbols: list[dict[str, Any]],
    *,
    use_network: bool,
    log_dir: str | Path | None = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
    ethbtc = next((record for record in symbols if record["symbol"] == KEY_ROTATION_PAIR), None)
    if ethbtc is None:
        ethbtc = _symbol_intelligence(use_network=use_network, log_dir=get_log_dir(log_dir, use_env=True), timeout=timeout, symbol=KEY_ROTATION_PAIR)[0]
    change = _float_or_none(ethbtc.get("price_change_percent_24h"))
    if change is None:
        state = "UNKNOWN"
    elif change >= 1.0:
        state = "ETH_LEADING_BTC"
    elif change <= -1.0:
        state = "ETH_LAGGING_BTC"
    else:
        state = "ETH_NEUTRAL_VS_BTC"
    return {
        "key_rotation_pair": KEY_ROTATION_PAIR,
        "ethbtc_price": ethbtc.get("last_price"),
        "ethbtc_change_percent_24h": change,
        "rotation_state": state,
        "interpretation": "ETHBTC positive and strong can indicate ETH strength vs BTC / possible alt-cycle rotation.",
        "market_data_status": ethbtc.get("market_data_status"),
        "network_used": bool(use_network),
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
    }


def append_market_snapshot(snapshot: dict[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = _snapshots_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, sort_keys=True) + "\n")


def load_market_snapshots(*, limit: int = 50, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    path = _snapshots_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def build_market_snapshots_payload(*, limit: int = 50, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_market_snapshots(limit=limit, log_dir=log_dir)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "snapshots": records,
        "snapshots_count": len(records),
    }


def build_market_intelligence_summary_text(
    *,
    use_network: bool = False,
    write: bool = False,
    limit: int = 20,
    log_dir: str | Path | None = None,
) -> str:
    payload = build_market_intelligence_summary(use_network=use_network, write=write, limit=limit, log_dir=log_dir)
    return "\n".join(
        [
            "HAMMER RADAR MARKET INTELLIGENCE SUMMARY",
            "live_execution_enabled: false",
            "order_placed: false",
            f"network_used: {str(payload['network_used']).lower()}",
            f"market_data_status: {payload['market_data_status']}",
            f"key_rotation_pair: {payload['key_rotation_pair']}",
            f"ethbtc_rotation_state: {payload['ethbtc_rotation_state']}",
            f"top_ranked_symbols: {', '.join(payload['top_ranked_symbols'])}",
            f"warning: {payload['warning']}",
        ]
    )


def build_market_rankings_text(
    *,
    use_network: bool = False,
    category: str | None = None,
    limit: int = 20,
    log_dir: str | Path | None = None,
) -> str:
    payload = build_market_rankings(use_network=use_network, category=category, limit=limit, log_dir=log_dir)
    lines = [
        "HAMMER RADAR MARKET INTELLIGENCE RANKINGS",
        "live_execution_enabled: false",
        "order_placed: false",
        f"market_data_status: {payload['market_data_status']}",
    ]
    for record in payload["ranked_symbols"]:
        lines.append(
            f"{record['rank']}. {record['symbol']} | score={record['market_intelligence_score']} | "
            f"momentum={record['momentum_score']} | liquidity={record['liquidity_score']} | "
            f"live_eligible_symbol={str(record['live_eligible_symbol']).lower()}"
        )
    return "\n".join(lines)


def build_ethbtc_rotation_text(*, use_network: bool = False, log_dir: str | Path | None = None) -> str:
    rotation = evaluate_ethbtc_rotation(use_network=use_network, log_dir=log_dir)
    return "\n".join(
        [
            "HAMMER RADAR ETHBTC ROTATION",
            "live_execution_enabled: false",
            "order_placed: false",
            f"key_rotation_pair: {rotation['key_rotation_pair']}",
            f"ethbtc_price: {rotation['ethbtc_price']}",
            f"ethbtc_change_percent_24h: {rotation['ethbtc_change_percent_24h']}",
            f"rotation_state: {rotation['rotation_state']}",
            f"interpretation: {rotation['interpretation']}",
        ]
    )


def build_market_snapshots_text(*, limit: int = 50, log_dir: str | Path | None = None) -> str:
    payload = build_market_snapshots_payload(limit=limit, log_dir=log_dir)
    lines = [
        "HAMMER RADAR MARKET INTELLIGENCE SNAPSHOTS",
        "live_execution_enabled: false",
        "order_placed: false",
        f"snapshots_count: {payload['snapshots_count']}",
    ]
    if not payload["snapshots"]:
        return "\n".join([*lines, "no market intelligence snapshots"])
    for record in payload["snapshots"]:
        lines.append(
            f"{record.get('created_at')} | {record.get('snapshot_id')} | status={record.get('market_data_status')} | "
            f"network_used={record.get('network_used')} | rotation={record.get('ethbtc_rotation_state')}"
        )
    return "\n".join(lines)


def _symbol_intelligence(
    *,
    use_network: bool,
    log_dir: Path,
    timeout: float,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    watchlist = build_watchlist(limit=0, log_dir=log_dir)["symbols"]
    if symbol is not None:
        watchlist = [record for record in watchlist if record["symbol"] == symbol]
    return [_build_symbol_record(record, use_network=use_network, timeout=timeout) for record in watchlist]


def _build_symbol_record(watch_record: dict[str, Any], *, use_network: bool, timeout: float) -> dict[str, Any]:
    ticker, ticker_status = _ticker_or_fallback(watch_record["symbol"], use_network=use_network, timeout=timeout)
    rules = STATIC_RULES.get(watch_record["symbol"], {})
    change = _float_or_none(ticker.get("priceChangePercent"))
    quote_volume = _float_or_none(ticker.get("quoteVolume"))
    momentum_score = _momentum_adjustment(change, symbol=watch_record["symbol"])
    liquidity_score = 10 if quote_volume is not None and quote_volume >= _volume_threshold(watch_record["symbol"]) else 0
    score = max(0, min(100, int(watch_record.get("watch_score") or 0) + momentum_score + liquidity_score))
    return {
        "symbol": watch_record["symbol"],
        "category": watch_record["category"],
        "pair_type": watch_record["pair_type"],
        "current_phase_permission": watch_record["current_phase_permission"],
        "live_eligible_symbol": watch_record["live_eligible_symbol"],
        "paper_watch_enabled": watch_record["paper_watch_enabled"],
        "watch_only": watch_record["watch_only"],
        "market_data_status": ticker_status,
        "last_price": _float_or_none(ticker.get("lastPrice")),
        "price_change_percent_24h": change,
        "quote_volume_24h": quote_volume,
        "volume_24h": _float_or_none(ticker.get("volume")),
        "high_price_24h": _float_or_none(ticker.get("highPrice")),
        "low_price_24h": _float_or_none(ticker.get("lowPrice")),
        "exchange_info_status": "STATIC_FALLBACK" if rules else "UNKNOWN_RULES",
        "symbol_supported": watch_record["symbol"] in STATIC_RULES or watch_record["symbol"].endswith("USDT") or watch_record["symbol"] == KEY_ROTATION_PAIR,
        "min_notional_usd": rules.get("min_notional_usd"),
        "tick_size": rules.get("tick_size"),
        "step_size": rules.get("step_size"),
        "momentum_score": momentum_score,
        "liquidity_score": liquidity_score,
        "market_intelligence_score": score,
        "rank_reason": _rank_reason(watch_record, change=change, quote_volume=quote_volume, momentum_score=momentum_score, liquidity_score=liquidity_score),
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
    }


def _ticker_or_fallback(symbol: str, *, use_network: bool, timeout: float) -> tuple[dict[str, Any], str]:
    if not use_network:
        return {}, "FALLBACK_ONLY"
    try:
        return fetch_ticker(symbol, timeout=timeout), "OK"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return {}, "MARKET_DATA_UNAVAILABLE"


def _summary_status(records: list[dict[str, Any]], *, network_used: bool) -> str:
    statuses = {record.get("market_data_status") for record in records}
    if not network_used:
        return "FALLBACK_ONLY"
    if statuses == {"OK"}:
        return "OK"
    if "OK" in statuses:
        return "PARTIAL"
    return "MARKET_DATA_UNAVAILABLE"


def _momentum_adjustment(change: float | None, *, symbol: str) -> int:
    if change is None:
        return 0
    if change >= 8.0:
        score = 15
    elif change >= 4.0:
        score = 10
    elif change >= 1.0:
        score = 5
    elif change <= -8.0:
        score = -15
    elif change <= -4.0:
        score = -10
    elif change <= -1.0:
        score = -5
    else:
        score = 0
    if symbol == KEY_ROTATION_PAIR and change > 1.0:
        score += 5
    return score


def _volume_threshold(symbol: str) -> float:
    return 10_000_000.0 if symbol.endswith("USDT") else 500.0


def _rank_reason(
    watch_record: dict[str, Any],
    *,
    change: float | None,
    quote_volume: float | None,
    momentum_score: int,
    liquidity_score: int,
) -> str:
    return (
        f"base_watch_score={watch_record.get('watch_score')}; "
        f"price_change_percent_24h={change}; momentum_score={momentum_score}; "
        f"quote_volume_24h={quote_volume}; liquidity_score={liquidity_score}"
    )


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _snapshot_id() -> str:
    created_at = datetime.now(UTC).isoformat()
    digest = hashlib.sha256(f"{SOURCE}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"mi_{digest}"


def _snapshots_path(log_dir: Path) -> Path:
    return log_dir / SNAPSHOTS_FILENAME
