# R154 Promotion Candidate Audit From Expanded Paper

Phase: R154

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: EXTENSION OF EXISTING CAPABILITY, WIRING / INTEGRATION, DUPLICATE RISK
- Duplicate risk level: HIGH

## Why R154 Follows R153

R151 proved the fresh-candidate watcher was healthy but too narrow. R152 expanded BTCUSDT paper-only visibility across 4m/8m/13m/44m long and short lanes while preserving the existing 13m/44m long `tiny_live` lanes. R153 made that expanded paper scope observable and append-only.

R154 consumes that local paper evidence and recent outcome surfaces to rank lane families for future review. It does not promote lanes and does not change config.

## Paper Evidence Ranking

Command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  promotion-candidate-audit \
  --latest-outcomes 5000 \
  --latest-signals 2000 \
  --latest-watch-records 200 \
  --include-paper-lanes \
  --include-tiny-live-incumbents
```

The audit reads local-only surfaces:

- `configs/hammer_radar/lane_controls.json`
- `logs/hammer_radar_forward/outcomes.ndjson`
- `logs/hammer_radar_forward/paper_executions.ndjson`
- `logs/hammer_radar_forward/expanded_paper_watch.ndjson`
- `logs/hammer_radar_forward/signals.ndjson`
- `logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson`

For each included lane family it reports paper outcome counts, win/loss/stop counts, win rate, average and total PnL, fill rate when inferable, fresh/stale candidate counts, freshness hit rate, sample quality, score, readiness, risks, and a next action.

## Threshold Meaning

R154 uses conservative review thresholds:

- At least 30 paper outcomes before strong consideration.
- At least 10 fresh candidates before strong consideration.
- Win rate of 52% or better is preferred.
- Average PnL should be positive.
- Stop hits should not dominate.
- Freshness hit rate should be non-zero.

Missing fields are not invented. Missing or low samples produce `NOT_ENOUGH_EVIDENCE`, `PAPER_ONLY_CONTINUE_COLLECTING`, or manual-review classifications.

## No Lane Promotion Here

R154 is an audit only. It never:

- sets a lane to `tiny_live`
- applies lane mode changes
- changes existing tiny-live lane modes
- authorizes live shorts
- writes lane config
- enables global live flags
- disables the kill switch
- creates order payloads
- calls Binance
- places orders

Confirmed recording appends only:

```text
logs/hammer_radar_forward/promotion_candidate_audits.ndjson
```

## Recording Evidence

Rejected confirmation check:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  promotion-candidate-audit \
  --record-audit \
  --confirm-promotion-audit "wrong"
```

Confirmed record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  promotion-candidate-audit \
  --latest-outcomes 5000 \
  --latest-signals 2000 \
  --latest-watch-records 200 \
  --include-paper-lanes \
  --include-tiny-live-incumbents \
  --record-audit \
  --confirm-promotion-audit "I CONFIRM PROMOTION CANDIDATE AUDIT RECORDING ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."
```

## Short Lanes

Short lanes can rank as paper watchlist or strong paper candidates, but they remain paper-only. A future short `tiny_live` proposal requires a separate short strategy review covering opposite golden pocket as resistance, short-specific stop/TP policy, and explicit operator approval.

## Safe Commands

R154 output includes only safe commands:

- expanded-paper-watch preview
- expanded-paper-watch record
- promotion-candidate-audit record
- candidate-source-freshness-audit

It does not emit live connector commands or lane mode apply commands.

## Next Possible Phase

R155 should branch from the R154 result:

- If the strongest evidence is short, run a short strategy review only.
- If the strongest evidence is a long paper lane, build a promotion packet only.
- No lane mode change occurs without a later explicit operator approval phase.
- No live execution occurs.
