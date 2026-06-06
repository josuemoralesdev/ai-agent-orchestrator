# R216 Betrayal Source Emitter Refresh

## Purpose

Refresh betrayal source emission so future paper events carry explicit direction split schema:

- `original_direction`
- `inverse_direction` or `betrayal_direction`
- `entry_mode`
- `source_signal_id`
- `signal_timestamp`
- deterministic source identity

## Scope

- Reuse R96 deterministic betrayal paper identity rules.
- Reuse R100 source emitter direction-entry-mode matching rules.
- Read local ledgers only.
- Emit or preview paper-only rows only after exact confirmation if a write path is added.
- Keep aggregate identities separate from direction-entry-mode identities.
- Do not treat lane-key direction alone as original/inverse proof.
- Do not fabricate directions, entries, exits, or outcomes.

## Non-Negotiable Safety

- No config writes.
- No env writes or mutations.
- No Binance calls.
- No network calls.
- No order payloads.
- No order placement.
- No live execution.
- No kill switch changes.
- No lane mode changes.
- No `tiny_live` writes.
- No risk contract writes.
- No signal origin promotion.
- No lane promotion.
- No betrayal promotion.
- No live authorization.

## Expected Output

- Source emitter refresh preview.
- Explicit direction schema coverage summary.
- Rows skipped because they remain aggregate-only.
- Gap report for missing original direction, betrayal direction, entry mode, source identity, and signal timestamp.
- Safety object proving no live/config/order/network behavior occurred.

## Suggested Command

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-source-emitter-refresh
```

## Validation

- Run focused tests for the R216 module and CLI.
- Run R215, R212, R211, R210, R100, and R96 related tests.
- Confirm env/config diffs remain empty.
