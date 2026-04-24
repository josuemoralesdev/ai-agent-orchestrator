"""Strategy truth extraction CLI for Hammer Radar archived signals and outcomes."""

from __future__ import annotations

import argparse

from src.app.hammer_radar.operator.archive import load_outcomes, load_signals
from src.app.hammer_radar.operator.strategy_config import filter_summary_rows_for_strategy
from src.app.hammer_radar.operator.stats import build_setup_summary


def build_truth_summary_text(*, tradable_only: bool = False) -> str:
    rows = _load_summary_rows(tradable_only=tradable_only)
    signals = load_signals()
    outcomes = load_outcomes()
    fills = sum(row["fills"] for row in rows)
    wins = sum(row["wins"] for row in rows)
    losses = sum(row["losses"] for row in rows)
    stops = sum(row["stops"] for row in rows)
    total_samples = sum(row["samples"] for row in rows)
    avg_pnl_pct = _weighted_average(rows, "avg_pnl_pct", weight_key="fills")
    avg_mae_pct = _weighted_average(rows, "avg_mae_pct", weight_key="fills")
    avg_mfe_pct = _weighted_average(rows, "avg_mfe_pct", weight_key="fills")

    label = "HAMMER RADAR TRUTH SUMMARY [tradable_only]" if tradable_only else "HAMMER RADAR TRUTH SUMMARY"
    lines = [
        label,
        f"signals: {sum(1 for signal in signals if signal.tradable) if tradable_only else len(signals)}",
        f"outcomes: {len(outcomes)}",
        f"setup_groups: {len(rows)}",
        f"samples: {total_samples}",
        f"fills: {fills}",
        f"wins: {wins}",
        f"losses: {losses}",
        f"stops: {stops}",
        f"fill_rate: {_format_pct((fills / total_samples) * 100.0) if total_samples else '0.00%'}",
        f"win_rate_on_filled: {_format_pct((wins / fills) * 100.0) if fills else '0.00%'}",
        f"avg_pnl_pct: {_format_pct(avg_pnl_pct, digits=4)}",
        f"avg_mae_pct: {_format_pct(avg_mae_pct, digits=4)}",
        f"avg_mfe_pct: {_format_pct(avg_mfe_pct, digits=4)}",
    ]
    return "\n".join(lines)


def build_top_setups_text(*, limit: int, min_samples: int, tradable_only: bool = False) -> str:
    rows = _filter_by_min_samples(_load_summary_rows(tradable_only=tradable_only), min_samples=min_samples)
    ranked = sorted(
        rows,
        key=lambda row: (
            -row["win_rate_on_filled"],
            -row["avg_pnl_pct"],
            -row["samples"],
        ),
    )
    title = "HAMMER RADAR TOP SETUPS [tradable_only]" if tradable_only else "HAMMER RADAR TOP SETUPS"
    return _format_summary_rows(title, ranked, limit=limit, min_samples=min_samples)


def build_weak_setups_text(*, limit: int, min_samples: int, tradable_only: bool = False) -> str:
    rows = _filter_by_min_samples(_load_summary_rows(tradable_only=tradable_only), min_samples=min_samples)
    ranked = sorted(
        rows,
        key=lambda row: (
            row["avg_pnl_pct"],
            row["win_rate_on_filled"],
            -row["samples"],
        ),
    )
    title = "HAMMER RADAR WEAK SETUPS [tradable_only]" if tradable_only else "HAMMER RADAR WEAK SETUPS"
    return _format_summary_rows(title, ranked, limit=limit, min_samples=min_samples)


def build_grouped_truth_text(group_key: str, *, tradable_only: bool = False) -> str:
    rows = _load_summary_rows(tradable_only=tradable_only)
    grouped = _group_rows(rows, group_key=group_key)
    title = f"HAMMER RADAR TRUTH BY {group_key.upper()}"
    if tradable_only:
        title += " [tradable_only]"
    return _format_group_rows(title, grouped)


def build_strategy_eligible_text(*, limit: int, min_samples: int) -> str:
    rows = filter_summary_rows_for_strategy(_load_summary_rows(tradable_only=False))
    rows = _filter_by_min_samples(rows, min_samples=min_samples)
    ranked = sorted(
        rows,
        key=lambda row: (
            -row["win_rate_on_filled"],
            -row["avg_pnl_pct"],
            -row["samples"],
        ),
    )
    return _format_summary_rows("HAMMER RADAR STRATEGY ELIGIBLE", ranked, limit=limit, min_samples=min_samples)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "summary":
        print(build_truth_summary_text())
    elif args.command == "top-setups":
        print(build_top_setups_text(limit=args.limit, min_samples=args.min_samples))
    elif args.command == "weak-setups":
        print(build_weak_setups_text(limit=args.limit, min_samples=args.min_samples))
    elif args.command == "by-entry-mode":
        print(build_grouped_truth_text("entry_mode"))
    elif args.command == "by-timeframe":
        print(build_grouped_truth_text("timeframe"))
    elif args.command == "strategy-eligible":
        print(build_strategy_eligible_text(limit=args.limit, min_samples=args.min_samples))
    elif args.command == "tradable-only":
        print(build_truth_summary_text(tradable_only=True))
        print()
        print(build_top_setups_text(limit=args.limit, min_samples=args.min_samples, tradable_only=True))
    else:
        parser.error(f"unsupported command: {args.command}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.truth")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("summary")

    top_parser = subparsers.add_parser("top-setups")
    top_parser.add_argument("--limit", type=int, default=10)
    top_parser.add_argument("--min-samples", type=int, default=3)

    weak_parser = subparsers.add_parser("weak-setups")
    weak_parser.add_argument("--limit", type=int, default=10)
    weak_parser.add_argument("--min-samples", type=int, default=3)

    subparsers.add_parser("by-entry-mode")
    subparsers.add_parser("by-timeframe")

    strategy_parser = subparsers.add_parser("strategy-eligible")
    strategy_parser.add_argument("--limit", type=int, default=10)
    strategy_parser.add_argument("--min-samples", type=int, default=3)

    tradable_parser = subparsers.add_parser("tradable-only")
    tradable_parser.add_argument("--limit", type=int, default=10)
    tradable_parser.add_argument("--min-samples", type=int, default=3)

    return parser


def _load_summary_rows(*, tradable_only: bool) -> list[dict]:
    return build_setup_summary(load_signals(), load_outcomes(), tradable_only=tradable_only)


def _filter_by_min_samples(rows: list[dict], *, min_samples: int) -> list[dict]:
    return [row for row in rows if row["samples"] >= max(min_samples, 0)]


def _group_rows(rows: list[dict], *, group_key: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for row in rows:
        key = str(row.get(group_key, ""))
        bucket = grouped.setdefault(
            key,
            {
                "group": key,
                "samples": 0,
                "fills": 0,
                "wins": 0,
                "losses": 0,
                "stops": 0,
                "pnl_total": 0.0,
                "mae_total": 0.0,
                "mfe_total": 0.0,
            },
        )
        bucket["samples"] += row["samples"]
        bucket["fills"] += row["fills"]
        bucket["wins"] += row["wins"]
        bucket["losses"] += row["losses"]
        bucket["stops"] += row["stops"]
        bucket["pnl_total"] += row["avg_pnl_pct"] * row["fills"]
        bucket["mae_total"] += row["avg_mae_pct"] * row["fills"]
        bucket["mfe_total"] += row["avg_mfe_pct"] * row["fills"]

    result: list[dict] = []
    for bucket in grouped.values():
        fills = bucket["fills"]
        samples = bucket["samples"]
        result.append(
            {
                "group": bucket["group"],
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
    return sorted(result, key=lambda row: (-row["samples"], -row["avg_pnl_pct"], row["group"]))


def _format_summary_rows(title: str, rows: list[dict], *, limit: int, min_samples: int) -> str:
    if not rows:
        return f"{title}\nno setups matched min_samples={min_samples}"

    lines = [f"{title} | min_samples={min_samples}"]
    for row in rows[: max(limit, 0)]:
        lines.append(
            " | ".join(
                [
                    f"{row['timeframe']} {row['direction'].upper()}",
                    f"bias={'Y' if row['bias_aligned'] else 'N'}",
                    f"strength={row['strength_band']}",
                    f"trend={row['trend_direction'] or 'na'}/{row['trend_strength_band'] or 'na'}",
                    f"ema={row['price_vs_ema_4h_pct_band'] or 'na'}",
                    f"entry={row['entry_mode']}",
                    f"samples={row['samples']}",
                    f"fills={row['fills']}",
                    f"fill_rate={_format_pct(row['fill_rate'])}",
                    f"wins={row['wins']}",
                    f"losses={row['losses']}",
                    f"stops={row['stops']}",
                    f"win_rate={_format_pct(row['win_rate_on_filled'])}",
                    f"avg_pnl={_format_pct(row['avg_pnl_pct'], digits=4)}",
                    f"avg_mae={_format_pct(row['avg_mae_pct'], digits=4)}",
                    f"avg_mfe={_format_pct(row['avg_mfe_pct'], digits=4)}",
                ]
            )
        )
    return "\n".join(lines)


def _format_group_rows(title: str, rows: list[dict]) -> str:
    if not rows:
        return f"{title}\nno grouped rows"

    lines = [title]
    for row in rows:
        lines.append(
            " | ".join(
                [
                    row["group"] or "na",
                    f"samples={row['samples']}",
                    f"fills={row['fills']}",
                    f"fill_rate={_format_pct(row['fill_rate'])}",
                    f"wins={row['wins']}",
                    f"losses={row['losses']}",
                    f"stops={row['stops']}",
                    f"win_rate={_format_pct(row['win_rate_on_filled'])}",
                    f"avg_pnl={_format_pct(row['avg_pnl_pct'], digits=4)}",
                    f"avg_mae={_format_pct(row['avg_mae_pct'], digits=4)}",
                    f"avg_mfe={_format_pct(row['avg_mfe_pct'], digits=4)}",
                ]
            )
        )
    return "\n".join(lines)


def _weighted_average(rows: list[dict], value_key: str, *, weight_key: str) -> float:
    total_weight = sum(row[weight_key] for row in rows)
    if total_weight == 0:
        return 0.0
    total = sum(row[value_key] * row[weight_key] for row in rows)
    return round(total / total_weight, 4)


def _format_pct(value: float, digits: int = 2) -> str:
    return f"{float(value):.{digits}f}%"


if __name__ == "__main__":
    raise SystemExit(main())
