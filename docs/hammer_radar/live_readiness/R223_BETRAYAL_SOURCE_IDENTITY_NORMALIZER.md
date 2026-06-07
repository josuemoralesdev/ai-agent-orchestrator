# R223 Betrayal Source Identity Normalizer

R223 adds a paper-only source identity normalizer for betrayal source rows. It reads the R218 registry, R221 consumer refactor report, R219 registry wiring, R217 aggregate decomposition, R216 source emitter refresh, R215 direction split resolver, and R212 event tracker ledgers.

Command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-source-identity-normalizer
```

Append-only recording requires the exact phrase:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-source-identity-normalizer \
  --record-normalizer \
  --confirm-betrayal-source-identity-normalizer "I CONFIRM BETRAYAL SOURCE IDENTITY NORMALIZER RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Ledger:

```text
logs/hammer_radar_forward/betrayal_source_identity_normalizer.ndjson
```

## Scope

- Normalizes `entry_mode`, `source_identity`, `source_signal_id`, `emitted_signal_id`, `lane_key`, and `emitted_direction` only when local evidence supports the field.
- Validates normalized rows against the R218/R219 registry-backed `betrayal_source_emitter_v2` requirements.
- Classifies rows as `normalizer_ready`, `partial_normalization`, `blocked_missing_identity`, `blocked_missing_entry_mode`, or `blocked_aggregate_context_only`.
- Keeps every row paper-only with `live_authorized=false` and `promotion_allowed=false`.

## Non-Goals

R223 does not write configs, mutate env files, call Binance/network, create order payloads, place orders, disable the kill switch, set lane modes, promote betrayal, authorize live, infer tiny-live readiness, or count normalized rows as resolved outcomes.

## Follow-Up

R224 should append normalized v2 source rows only when R223 reports resolver-ready rows. R214 should remain the paper-only event outcome resolver after append-only source rows exist.
