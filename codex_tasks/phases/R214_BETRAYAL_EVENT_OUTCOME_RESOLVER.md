# R214 Betrayal Event Outcome Resolver

## Purpose

Resolve tracked R212 betrayal events into future paper outcomes using local
evidence only.

## Scope

- Read `logs/hammer_radar_forward/betrayal_event_tracker.ndjson`.
- Read local candle archives for the tracked event timeframes.
- Read local betrayal paper signals, shadow outcomes, shadow resolutions, and
  true paper outcomes when present.
- Resolve only future paper outcomes with deterministic event identity linkage.
- Keep aggregate context separate from direction-specific proof.
- Do not count raw captures as resolved samples.
- Do not fabricate candles, events, entries, exits, or outcomes.

## Non-Negotiable Safety

- No Binance calls.
- No network calls.
- No order payloads.
- No order placement.
- No env writes or mutations.
- No config writes.
- No lane mode changes.
- No risk contract writes.
- No registry or scoring config writes.
- No signal origin promotion.
- No lane promotion.
- No betrayal promotion.
- No live authorization.
- No tiny-live readiness inference.
- Keep kill switch behavior intact.

## Expected Output

- Resolver preview over tracked R212 events.
- Event outcome status per tracked identity.
- Paper-only resolved outcome records only after exact future confirmation.
- Gap report for missing candles, unresolved windows, missing direction split,
  and aggregate-only events.
- Safety object proving no live/config/order/network behavior occurred.

## Suggested Command

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-event-outcome-resolver
```

## Validation

- Run focused tests for the new R214 resolver module and CLI.
- Run R212, R211, R210, and R209 related tests.
- Confirm env/config/feed diffs remain empty except append-only R214 ledger when
  explicitly recorded.
