# R221 Betrayal Registry Consumer Refactor

R221 refactors betrayal-family consumer surfaces to read the R218 strategy evidence registry and R219 betrayal registry wiring outputs as paper-only source-of-truth context.

## Runtime Surface

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-registry-consumer-refactor
```

Recording is append-only to `logs/hammer_radar_forward/betrayal_registry_consumer_refactor.ndjson` and requires:

```text
I CONFIRM BETRAYAL REGISTRY CONSUMER REFACTOR RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL.
```

## What Changed

- Added `betrayal_registry_consumer_refactor` as a compatibility and gap reporting surface.
- Added small registry consumer helpers to:
  - `betrayal_source_emitter_refresh`
  - `betrayal_aggregate_decomposition`
  - `betrayal_direction_split_resolver`
  - `betrayal_event_tracker`
- The target consumers now expose registry-backed candidate, required-field, and safety-default consumption where safe.
- Audit-only modules remain reported for hardcoded target-list gaps without heavy refactor.

## Safety

R221 does not write env files, mutate configs, call Binance/network, create order payloads, place orders, promote betrayal, change lane modes, disable kill switches, infer live readiness, or authorize live.

Registry inclusion remains paper-only evidence context. R219 source identity and entry-mode blockers still require future local-evidence normalization work.

## Follow-Up

- R222 should refactor pattern, anchor, and normal matrix consumers to use the registry.
- R223 should normalize betrayal `source_identity` and `entry_mode` only where local evidence supports it.
