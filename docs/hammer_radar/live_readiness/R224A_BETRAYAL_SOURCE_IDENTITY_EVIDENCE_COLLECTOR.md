# R224A Betrayal Source Identity Evidence Collector

R224A adds a paper-only evidence collector for betrayal source identity blockers. It reads R223/R221/R219/R218/R217/R216/R215/R212 local outputs plus local full-spectrum, shadow outcome, and paper signal ledgers.

Command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-source-identity-evidence-collector
```

Append-only collector recording requires:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-source-identity-evidence-collector \
  --record-collector \
  --confirm-betrayal-source-identity-evidence-collector "I CONFIRM BETRAYAL SOURCE IDENTITY EVIDENCE COLLECTOR RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Ledger:

```text
logs/hammer_radar_forward/betrayal_source_identity_evidence_collector.ndjson
```

## Scope

- Collects explicit or defensible local evidence for `entry_mode`, `source_identity`, `source_signal_id`, `source_capture_id`, `emitted_signal_id`, `lane_key`, direction, and source family.
- Classifies evidence as explicit, lane-key derived, signal-id derived, deterministic from complete local fields, or insufficient.
- Previews emitted signal ids and lane keys only when required local fields are present.
- Uses the R218/R219 betrayal source registry contract for `resolver_ready_preview`.
- Does not append normalized v2 rows. R224 remains the append phase.

## Safety

R224A does not write configs, mutate env files, call Binance/network, create order payloads, place orders, transfer, withdraw, change live flags, disable kill switches, change lane modes, write risk contracts, promote betrayal, promote any signal origin or lane, infer tiny-live readiness, or authorize live execution.

Every output row remains `paper_only=true`, `live_authorized=false`, and `promotion_allowed=false`.

## Current Operational Meaning

If `resolver_ready_preview_rows=0`, R224 must not run. Continue source evidence collection and wire future emitters to make `entry_mode` and source identity fields explicit.
