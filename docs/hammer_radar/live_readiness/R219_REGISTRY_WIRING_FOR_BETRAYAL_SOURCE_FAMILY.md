# R219 Registry Wiring For Betrayal Source Family

R219 adds a paper-only registry wiring audit for the betrayal source family. It reads the R218 strategy evidence registry, then validates R217 aggregate decomposition, R216 source emitter refresh, and R215 direction split resolver rows against the registry-backed betrayal source identity contract.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  registry-wiring-betrayal-source-family
```

Append-only record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  registry-wiring-betrayal-source-family \
  --record-wiring \
  --confirm-registry-wiring-betrayal-source-family "I CONFIRM REGISTRY WIRING BETRAYAL SOURCE FAMILY RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Wrong confirmations return `REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_REJECTED` and write no ledger row.

## Registry Wiring

The R218 registry is the authority for:

- betrayal candidates
- active timeframes
- valid and blocked entry modes
- `betrayal_source_emitter_v2` required fields
- betrayal evidence requirements
- paper-only, live-disabled, no-promotion safety defaults

If the R218 registry ledger is missing or invalid, R219 returns blocked and does not proceed as ready.

## Validation

A source row is registry-valid only when it satisfies the full `betrayal_source_emitter_v2` field list, remains `paper_only=true`, keeps `live_authorized=false` and `promotion_allowed=false`, matches a registry candidate/timeframe, uses a non-placeholder registry entry mode, and has explicit original/inverse/emitted direction where emitted direction equals inverse direction.

Rows missing entry mode, source identity, source signal id, event identity, event hash, or direction fields remain paper context only and are blocked from resolver-ready status.

## Output

The JSON output includes:

- `registry_backed_betrayal_candidate_view`
- `candidate_registry_validation`
- `source_row_registry_validation`
- `registry_backed_missing_field_report`
- `registry_wiring_gap_report`
- `registry_wiring_recommendations`
- `wiring_status`
- `safety`

The append-only ledger is:

```text
logs/hammer_radar_forward/registry_wiring_betrayal_source_family.ndjson
```

## Safety

R219 is registry wiring and audit only. It cannot call Binance or network, create order or executable payloads, sign requests, place orders, transfer, withdraw, write env/config/risk/lane/registry/scoring/matrix state, disable the kill switch, set any lane `tiny_live`, promote betrayal, promote signal origins or lanes, infer tiny-live readiness, or authorize live execution.

## Current Result

R219 can prove the betrayal candidate scope and required v2 source fields are registry-backed. Remaining blocker reports are expected while R217/R216/R215 local rows still lack entry mode, source identity, source signal identity, event identity, or complete direction schema.

## Next Phases

- R220 should wire pattern and anchor families to consume the R218 registry.
- R221 should refactor betrayal source emitter, decomposition, and event tracker consumers to consume R218 registry candidates and required fields directly.
