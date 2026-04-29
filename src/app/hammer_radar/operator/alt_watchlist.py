"""ETH and alt watchlist scanner for Hammer Radar.

R30 is watchlist and paper-only for ETH, ETHBTC, and alts. BTCUSDT remains the
only live-readiness symbol.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir, load_signals
from src.app.hammer_radar.operator.inspect import build_live_candidate_snapshot

LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False

CORE_LIVE = "CORE_LIVE"
CORE_WATCH = "CORE_WATCH"
RELATIVE_STRENGTH = "RELATIVE_STRENGTH"
LIQUID_MAJOR = "LIQUID_MAJOR"
HIGH_BETA = "HIGH_BETA"

BTC_LIVE_STACK = "BTC_LIVE_STACK"
USDT_PERP_WATCH = "USDT_PERP_WATCH"
BTC_RELATIVE_STRENGTH = "BTC_RELATIVE_STRENGTH"

ETH_PAPER_WATCH = "ETH_PAPER_WATCH"
RELATIVE_STRENGTH_WATCH = "RELATIVE_STRENGTH_WATCH"
ALT_PAPER_WATCH = "ALT_PAPER_WATCH"
WATCH_ONLY_UNKNOWN_RULES = "WATCH_ONLY_UNKNOWN_RULES"

WATCHLIST_BY_CATEGORY: dict[str, list[str]] = {
    CORE_LIVE: ["BTCUSDT"],
    CORE_WATCH: ["ETHUSDT"],
    RELATIVE_STRENGTH: ["ETHBTC"],
    LIQUID_MAJOR: ["SOLUSDT", "BNBUSDT", "XRPUSDT", "LINKUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"],
    HIGH_BETA: ["SUIUSDT", "NEARUSDT", "OPUSDT", "ARBUSDT", "INJUSDT", "SEIUSDT", "TIAUSDT", "FETUSDT", "RNDRUSDT"],
}

WATCHLIST_SYMBOLS = [symbol for symbols in WATCHLIST_BY_CATEGORY.values() for symbol in symbols]
LIVE_ELIGIBLE_SYMBOLS = {"BTCUSDT"}
KNOWN_USDT_WATCH_SYMBOLS = {symbol for symbol in WATCHLIST_SYMBOLS if symbol.endswith("USDT")}


@dataclass(frozen=True)
class SymbolConfig:
    symbol: str
    category: str
    pair_type: str
    live_eligible_symbol: bool
    paper_watch_enabled: bool
    watch_only: bool
    current_phase_permission: str
    reason: str


def build_watchlist(
    *,
    category: str | None = None,
    include_disabled: bool = True,
    limit: int = 50,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = [_symbol_record(config, log_dir=resolved_log_dir) for config in _symbol_configs()]
    if category is not None:
        records = [record for record in records if record["category"] == category]
    if not include_disabled:
        records = [record for record in records if record["watch_enabled"] is True]
    records.sort(key=lambda record: (-int(record["watch_score"]), int(record["rank"]), record["symbol"]))
    if limit > 0:
        records = records[:limit]
    for rank, record in enumerate(records, start=1):
        record["rank"] = rank
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "watchlist_count": len(records),
        "btc_live_only": True,
        "symbols": records,
    }


def build_watchlist_summary(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = build_watchlist(limit=0, log_dir=log_dir)["symbols"]
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "total_symbols": len(records),
        "core_live_count": _count_category(records, CORE_LIVE),
        "core_watch_count": _count_category(records, CORE_WATCH),
        "relative_strength_count": _count_category(records, RELATIVE_STRENGTH),
        "liquid_major_count": _count_category(records, LIQUID_MAJOR),
        "high_beta_count": _count_category(records, HIGH_BETA),
        "live_eligible_symbols": [record["symbol"] for record in records if record["live_eligible_symbol"]],
        "paper_watch_symbols": [record["symbol"] for record in records if record["paper_watch_enabled"]],
        "watch_only_symbols": [record["symbol"] for record in records if record["watch_only"]],
        "relative_strength_symbols": [record["symbol"] for record in records if record["pair_type"] == BTC_RELATIVE_STRENGTH],
        "btc_live_only": True,
        "next_promotion_candidate": "ETHUSDT",
        "key_rotation_pair": "ETHBTC",
        "warning": "ETHUSDT, ETHBTC, and alts are paper/watch-only in R30",
    }


def build_watchlist_text(
    *,
    category: str | None = None,
    limit: int = 50,
    log_dir: str | Path | None = None,
) -> str:
    payload = build_watchlist(category=category, limit=limit, log_dir=log_dir)
    lines = [
        "HAMMER RADAR ETH / ALT WATCHLIST",
        "live_execution_enabled: false",
        "order_placed: false",
        f"btc_live_only: {str(payload['btc_live_only']).lower()}",
        f"watchlist_count: {payload['watchlist_count']}",
    ]
    for record in payload["symbols"]:
        lines.append(
            f"{record['rank']}. {record['symbol']} | category={record['category']} | "
            f"score={record['watch_score']} | pair_type={record['pair_type']} | "
            f"permission={record['current_phase_permission']} | "
            f"live_eligible_symbol={str(record['live_eligible_symbol']).lower()} | "
            f"paper_watch_enabled={str(record['paper_watch_enabled']).lower()}"
        )
    return "\n".join(lines)


def build_watchlist_summary_text(*, log_dir: str | Path | None = None) -> str:
    summary = build_watchlist_summary(log_dir=log_dir)
    return "\n".join(
        [
            "HAMMER RADAR ETH / ALT WATCHLIST SUMMARY",
            "live_execution_enabled: false",
            "order_placed: false",
            f"total_symbols: {summary['total_symbols']}",
            f"core_live_count: {summary['core_live_count']}",
            f"core_watch_count: {summary['core_watch_count']}",
            f"relative_strength_count: {summary['relative_strength_count']}",
            f"liquid_major_count: {summary['liquid_major_count']}",
            f"high_beta_count: {summary['high_beta_count']}",
            f"live_eligible_symbols: {', '.join(summary['live_eligible_symbols'])}",
            f"paper_watch_symbols: {', '.join(summary['paper_watch_symbols'])}",
            f"watch_only_symbols: {', '.join(summary['watch_only_symbols'])}",
            f"relative_strength_symbols: {', '.join(summary['relative_strength_symbols'])}",
            f"btc_live_only: {str(summary['btc_live_only']).lower()}",
            f"next_promotion_candidate: {summary['next_promotion_candidate']}",
            f"key_rotation_pair: {summary['key_rotation_pair']}",
            f"warning: {summary['warning']}",
        ]
    )


def _symbol_configs() -> list[SymbolConfig]:
    configs: list[SymbolConfig] = []
    for category, symbols in WATCHLIST_BY_CATEGORY.items():
        for symbol in symbols:
            configs.append(_config_for_symbol(symbol, category=category))
    return configs


def _config_for_symbol(symbol: str, *, category: str) -> SymbolConfig:
    if symbol == "BTCUSDT":
        return SymbolConfig(
            symbol=symbol,
            category=category,
            pair_type=BTC_LIVE_STACK,
            live_eligible_symbol=True,
            paper_watch_enabled=True,
            watch_only=False,
            current_phase_permission=BTC_LIVE_STACK,
            reason="BTCUSDT remains the only live-readiness symbol in R30.",
        )
    if symbol == "ETHUSDT":
        return SymbolConfig(
            symbol=symbol,
            category=category,
            pair_type=USDT_PERP_WATCH,
            live_eligible_symbol=False,
            paper_watch_enabled=True,
            watch_only=True,
            current_phase_permission=ETH_PAPER_WATCH,
            reason="ETHUSDT is a paper/watch-only possible future promotion candidate.",
        )
    if symbol == "ETHBTC":
        return SymbolConfig(
            symbol=symbol,
            category=category,
            pair_type=BTC_RELATIVE_STRENGTH,
            live_eligible_symbol=False,
            paper_watch_enabled=True,
            watch_only=True,
            current_phase_permission=RELATIVE_STRENGTH_WATCH,
            reason="ETHBTC tracks ETH strength vs BTC and alt-cycle rotation.",
        )
    permission = ALT_PAPER_WATCH if symbol in KNOWN_USDT_WATCH_SYMBOLS else WATCH_ONLY_UNKNOWN_RULES
    return SymbolConfig(
        symbol=symbol,
        category=category,
        pair_type=USDT_PERP_WATCH if symbol.endswith("USDT") else BTC_RELATIVE_STRENGTH,
        live_eligible_symbol=False,
        paper_watch_enabled=True,
        watch_only=True,
        current_phase_permission=permission,
        reason="Alt symbol is watchlist/paper-only in R30. No alt live tickets or orders.",
    )


def _symbol_record(config: SymbolConfig, *, log_dir: Path) -> dict[str, Any]:
    signal_summary = _signal_summary(config.symbol, log_dir=log_dir)
    watch_score = _watch_score(config.category, signal_summary=signal_summary)
    base_asset, quote_asset = _split_symbol(config.symbol, pair_type=config.pair_type)
    return {
        "symbol": config.symbol,
        "category": config.category,
        "rank": WATCHLIST_SYMBOLS.index(config.symbol) + 1,
        "watch_score": watch_score,
        "watch_enabled": True,
        "paper_watch_enabled": config.paper_watch_enabled,
        "live_eligible_symbol": config.live_eligible_symbol,
        "watch_only": config.watch_only,
        "quote_asset": quote_asset,
        "base_asset": base_asset,
        "pair_type": config.pair_type,
        "current_phase_permission": config.current_phase_permission,
        "reason": config.reason,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        **signal_summary,
    }


def _signal_summary(symbol: str, *, log_dir: Path) -> dict[str, Any]:
    signals = [signal for signal in load_signals(log_dir) if signal.symbol == symbol]
    latest = max(signals, key=lambda signal: signal.timestamp, default=None)
    latest_decision = None
    latest_score = None
    if latest is not None and symbol == "BTCUSDT":
        snapshot = build_live_candidate_snapshot(
            limit=1000,
            since_hours=24,
            min_score=0,
            symbol=symbol,
            allow_short=False,
            allow_oversold=False,
            allow_trigger_flags=False,
            max_risk_usd=5.0,
            max_leverage=3.0,
            max_position_usd=44.0,
            fresh_minutes=30,
            allow_expired=True,
            latest_only=False,
            log_dir=log_dir,
        )
        for check in snapshot["checks"]:
            if check.candidate.signal.signal_id == latest.signal_id:
                latest_decision = check.decision
                latest_score = check.candidate.score
                break
    return {
        "recent_signal_count": len(signals),
        "recent_tradable_count": sum(1 for signal in signals if signal.tradable),
        "latest_signal_timestamp": latest.timestamp if latest is not None else None,
        "latest_direction": latest.direction if latest is not None else None,
        "latest_timeframe": latest.timeframe if latest is not None else None,
        "latest_score": latest_score,
        "latest_decision": latest_decision,
    }


def _watch_score(category: str, *, signal_summary: dict[str, Any]) -> int:
    base_scores = {
        CORE_LIVE: 100,
        RELATIVE_STRENGTH: 95,
        CORE_WATCH: 92,
        LIQUID_MAJOR: 70,
        HIGH_BETA: 60,
    }
    score = base_scores.get(category, 50)
    if int(signal_summary.get("recent_signal_count") or 0) > 0:
        score += 10
    if int(signal_summary.get("recent_tradable_count") or 0) > 0:
        score += 5
    return max(0, min(100, score))


def _split_symbol(symbol: str, *, pair_type: str) -> tuple[str, str]:
    if pair_type == BTC_RELATIVE_STRENGTH and symbol.endswith("BTC"):
        return symbol[: -len("BTC")], "BTC"
    if symbol.endswith("USDT"):
        return symbol[: -len("USDT")], "USDT"
    return symbol, "UNKNOWN"


def _count_category(records: list[dict[str, Any]], category: str) -> int:
    return sum(1 for record in records if record["category"] == category)
