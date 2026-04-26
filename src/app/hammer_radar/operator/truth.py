"""Strategy truth extraction CLI for Hammer Radar archived signals and outcomes."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.app.hammer_radar.operator.archive import get_log_dir, load_outcomes, load_signals
from src.app.hammer_radar.operator.positions import load_closed_positions
from src.app.hammer_radar.operator.strategy_config import filter_summary_rows_for_strategy
from src.app.hammer_radar.operator.stats import build_setup_summary


def build_truth_summary_text(*, tradable_only: bool = False, log_dir: str | Path | None = None) -> str:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    rows = _load_summary_rows(tradable_only=tradable_only, log_dir=resolved_log_dir)
    signals = load_signals(resolved_log_dir)
    outcomes = load_outcomes(resolved_log_dir)
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


def build_top_setups_text(
    *, limit: int, min_samples: int, tradable_only: bool = False, log_dir: str | Path | None = None
) -> str:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    rows = _filter_by_min_samples(
        _load_summary_rows(tradable_only=tradable_only, log_dir=resolved_log_dir),
        min_samples=min_samples,
    )
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


def build_weak_setups_text(
    *, limit: int, min_samples: int, tradable_only: bool = False, log_dir: str | Path | None = None
) -> str:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    rows = _filter_by_min_samples(
        _load_summary_rows(tradable_only=tradable_only, log_dir=resolved_log_dir),
        min_samples=min_samples,
    )
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


def build_grouped_truth_text(
    group_key: str, *, tradable_only: bool = False, log_dir: str | Path | None = None
) -> str:
    rows = _load_summary_rows(tradable_only=tradable_only, log_dir=get_log_dir(log_dir, use_env=True))
    grouped = _group_rows(rows, group_key=group_key)
    title = f"HAMMER RADAR TRUTH BY {group_key.upper()}"
    if tradable_only:
        title += " [tradable_only]"
    return _format_group_rows(title, grouped)


def build_rsi_state_truth_text(*, tradable_only: bool = False, log_dir: str | Path | None = None) -> str:
    rows = _group_outcomes_by_signal_metadata(
        group_key="rsi_state",
        tradable_only=tradable_only,
        log_dir=get_log_dir(log_dir, use_env=True),
    )
    title = "HAMMER RADAR TRUTH BY RSI_STATE"
    if tradable_only:
        title += " [tradable_only]"
    return _format_group_rows(title, rows)


def build_divergence_truth_text(*, tradable_only: bool = False, log_dir: str | Path | None = None) -> str:
    rows = _group_outcomes_by_signal_metadata(
        group_key="divergence",
        tradable_only=tradable_only,
        log_dir=get_log_dir(log_dir, use_env=True),
    )
    title = "HAMMER RADAR TRUTH BY DIVERGENCE"
    if tradable_only:
        title += " [tradable_only]"
    return _format_group_rows(title, rows)


def build_trigger_truth_text(*, tradable_only: bool = False, log_dir: str | Path | None = None) -> str:
    rows = _group_outcomes_by_signal_metadata(
        group_key="trigger",
        tradable_only=tradable_only,
        log_dir=get_log_dir(log_dir, use_env=True),
    )
    title = "HAMMER RADAR TRUTH BY TRIGGER"
    if tradable_only:
        title += " [tradable_only]"
    return _format_group_rows(title, rows)


def build_strategy_eligible_text(
    *, limit: int, min_samples: int, log_dir: str | Path | None = None
) -> str:
    rows = filter_summary_rows_for_strategy(
        _load_summary_rows(tradable_only=False, log_dir=get_log_dir(log_dir, use_env=True))
    )
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


def build_paper_exits_text(log_dir: str | Path | None = None) -> str:
    positions = load_closed_positions(get_log_dir(log_dir, use_env=True))
    grouped: dict[tuple[str, str, str], dict[str, float | int | str]] = {}
    for position in positions:
        key = (position.timeframe, position.direction, position.close_reason or "unknown")
        bucket = grouped.setdefault(
            key,
            {
                "timeframe": position.timeframe,
                "direction": position.direction,
                "close_reason": position.close_reason or "unknown",
                "samples": 0,
                "pnl_usd_total": 0.0,
                "pnl_pct_total": 0.0,
            },
        )
        bucket["samples"] += 1
        bucket["pnl_usd_total"] += float(position.pnl_usd or 0.0)
        bucket["pnl_pct_total"] += float(position.pnl_pct or 0.0)

    if not grouped:
        return "HAMMER RADAR PAPER EXITS\nno closed paper positions"

    rows = sorted(
        grouped.values(),
        key=lambda row: (-int(row["samples"]), str(row["timeframe"]), str(row["close_reason"])),
    )
    lines = ["HAMMER RADAR PAPER EXITS"]
    for row in rows:
        samples = int(row["samples"])
        avg_pnl_usd = float(row["pnl_usd_total"]) / samples if samples else 0.0
        avg_pnl_pct = float(row["pnl_pct_total"]) / samples if samples else 0.0
        lines.append(
            " | ".join(
                [
                    f"{row['timeframe']} {str(row['direction']).upper()}",
                    f"reason={row['close_reason']}",
                    f"samples={samples}",
                    f"avg_pnl_usd={avg_pnl_usd:.4f}",
                    f"avg_pnl_pct={avg_pnl_pct:.4f}%",
                ]
            )
        )
    return "\n".join(lines)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "summary":
        print(build_truth_summary_text(log_dir=args.log_dir))
    elif args.command == "top-setups":
        print(build_top_setups_text(limit=args.limit, min_samples=args.min_samples, log_dir=args.log_dir))
    elif args.command == "weak-setups":
        print(build_weak_setups_text(limit=args.limit, min_samples=args.min_samples, log_dir=args.log_dir))
    elif args.command == "by-entry-mode":
        print(build_grouped_truth_text("entry_mode", log_dir=args.log_dir))
    elif args.command == "by-timeframe":
        print(build_grouped_truth_text("timeframe", log_dir=args.log_dir))
    elif args.command == "by-rsi-state":
        print(build_rsi_state_truth_text(log_dir=args.log_dir))
    elif args.command == "by-divergence":
        print(build_divergence_truth_text(log_dir=args.log_dir))
    elif args.command == "by-trigger":
        print(build_trigger_truth_text(log_dir=args.log_dir))
    elif args.command == "strategy-eligible":
        print(build_strategy_eligible_text(limit=args.limit, min_samples=args.min_samples, log_dir=args.log_dir))
    elif args.command == "paper-exits":
        print(build_paper_exits_text(log_dir=args.log_dir))
    elif args.command == "tradable-only":
        print(build_truth_summary_text(tradable_only=True, log_dir=args.log_dir))
        print()
        print(
            build_top_setups_text(
                limit=args.limit,
                min_samples=args.min_samples,
                tradable_only=True,
                log_dir=args.log_dir,
            )
        )
    else:
        parser.error(f"unsupported command: {args.command}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.truth")
    parser.add_argument("--log-dir", default=None, help="Read Hammer Radar NDJSON files from this directory.")
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--log-dir",
        default=argparse.SUPPRESS,
        help="Read Hammer Radar NDJSON files from this directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("summary", parents=[parent])

    top_parser = subparsers.add_parser("top-setups", parents=[parent])
    top_parser.add_argument("--limit", type=int, default=10)
    top_parser.add_argument("--min-samples", type=int, default=3)

    weak_parser = subparsers.add_parser("weak-setups", parents=[parent])
    weak_parser.add_argument("--limit", type=int, default=10)
    weak_parser.add_argument("--min-samples", type=int, default=3)

    subparsers.add_parser("by-entry-mode", parents=[parent])
    subparsers.add_parser("by-timeframe", parents=[parent])
    subparsers.add_parser("by-rsi-state", parents=[parent])
    subparsers.add_parser("by-divergence", parents=[parent])
    subparsers.add_parser("by-trigger", parents=[parent])

    strategy_parser = subparsers.add_parser("strategy-eligible", parents=[parent])
    strategy_parser.add_argument("--limit", type=int, default=10)
    strategy_parser.add_argument("--min-samples", type=int, default=3)

    subparsers.add_parser("paper-exits", parents=[parent])

    tradable_parser = subparsers.add_parser("tradable-only", parents=[parent])
    tradable_parser.add_argument("--limit", type=int, default=10)
    tradable_parser.add_argument("--min-samples", type=int, default=3)

    return parser


def _load_summary_rows(*, tradable_only: bool, log_dir: str | Path | None = None) -> list[dict]:
    return build_setup_summary(load_signals(log_dir), load_outcomes(log_dir), tradable_only=tradable_only)


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


def _group_outcomes_by_signal_metadata(
    *, group_key: str, tradable_only: bool, log_dir: str | Path | None
) -> list[dict]:
    signals = load_signals(log_dir)
    signal_by_id = {signal.signal_id: signal for signal in signals}
    grouped: dict[str, dict] = {}
    for outcome in load_outcomes(log_dir):
        signal = signal_by_id.get(outcome.signal_id)
        if signal is None:
            continue
        if tradable_only and not signal.tradable:
            continue

        key = _metadata_group_value(signal, group_key)
        bucket = grouped.setdefault(key, _new_metric_bucket(key))
        bucket["samples"] += 1
        if outcome.fill_status in {"filled", "partial"}:
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

    return _finalize_metric_buckets(grouped.values())


def _metadata_group_value(signal: object, group_key: str) -> str:
    if group_key == "rsi_state":
        return str(getattr(signal, "rsi_state", None) or "missing")
    if group_key == "divergence":
        if getattr(signal, "divergence_type", None) is None and not _has_r9_metadata(signal):
            return "missing"
        divergence_type = getattr(signal, "divergence_type", None) or "none"
        confirmed = "Y" if getattr(signal, "divergence_confirmed", False) else "N"
        return f"type={divergence_type} confirmed={confirmed}"
    if group_key == "trigger":
        if not _has_r9_metadata(signal):
            return "missing"
        return " ".join(
            [
                f"extreme={'Y' if getattr(signal, 'extreme_trigger', False) else 'N'}",
                f"critical={'Y' if getattr(signal, 'critical_trigger', False) else 'N'}",
                f"micro_scalp={'Y' if getattr(signal, 'micro_scalp_candidate', False) else 'N'}",
                f"human_approval={'Y' if getattr(signal, 'requires_human_approval', False) else 'N'}",
            ]
        )
    raise ValueError(f"unsupported metadata group: {group_key}")


def _has_r9_metadata(signal: object) -> bool:
    return any(
        [
            getattr(signal, "rsi_value", None) is not None,
            getattr(signal, "rsi_state", None) is not None,
            getattr(signal, "divergence_type", None) is not None,
            getattr(signal, "extreme_trigger", False),
            getattr(signal, "critical_trigger", False),
            getattr(signal, "micro_scalp_candidate", False),
            getattr(signal, "requires_human_approval", False),
        ]
    )


def _new_metric_bucket(group: str) -> dict:
    return {
        "group": group,
        "samples": 0,
        "fills": 0,
        "wins": 0,
        "losses": 0,
        "stops": 0,
        "pnl_total": 0.0,
        "mae_total": 0.0,
        "mfe_total": 0.0,
    }


def _finalize_metric_buckets(buckets: object) -> list[dict]:
    result: list[dict] = []
    for bucket in buckets:
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
