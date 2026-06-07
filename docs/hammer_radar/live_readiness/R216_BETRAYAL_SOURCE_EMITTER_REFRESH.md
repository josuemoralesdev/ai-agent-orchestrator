# R216 Betrayal Source Emitter Refresh

R216 defines the refreshed paper-only betrayal source emitter contract for future resolver-ready betrayal rows.

It reads local R215 direction split resolver output, R212 event tracker identities, R211 paper matrix context, R210 true inverse context, and existing R100/R96 source-emitter/scaffold semantics. It does not mutate configs, env files, registries, scoring, matrix files, risk contracts, or lane modes.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-source-emitter-refresh
```

Append-only record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-source-emitter-refresh \
  --record-refresh \
  --confirm-betrayal-source-emitter-refresh "I CONFIRM BETRAYAL SOURCE EMITTER REFRESH RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Wrong confirmations return `BETRAYAL_SOURCE_EMITTER_REFRESH_REJECTED` and write no ledger row.

## Refreshed Contract

Future betrayal paper signal rows must use `schema_version=betrayal_source_emitter_v2` and include explicit:

- `original_direction`
- `inverse_direction`
- `emitted_direction`
- `entry_mode`
- `source_identity`
- `source_signal_id`
- `source_signal_timestamp`
- `betrayal_event_identity`
- `betrayal_event_identity_hash`
- `outcome_windows`

Rows remain `paper_only=true`, `live_authorized=false`, and `promotion_allowed=false`.

## Direction Rules

- `original_direction` must be explicit.
- `inverse_direction` must be the opposite of `original_direction`.
- `emitted_direction` must equal `inverse_direction`.
- Aggregate candidates must be decomposed into direction-specific candidates before resolver-ready rows can emit.
- Lane direction alone is not original/inverse proof.
- Incomplete rows remain `aggregate_context_only` or blocked from the event outcome resolver.

## Current Result

R215 found no fully resolved direction split and showed partial or aggregate-only evidence for:

- `222m aggregate`
- `88m aggregate`
- `55m aggregate`

R216 therefore reports `SOURCE_EMITTER_AGGREGATE_DECOMPOSITION_REQUIRED` until local source schema proves original/inverse direction, entry mode, source identity, signal timestamp, event identity, and outcome windows.

## Safety

R216 is schema refresh and audit only. It cannot place orders, create executable payloads, call Binance/network, transfer, withdraw, write env/config/risk/lane/registry/scoring/matrix state, disable the kill switch, set any lane `tiny_live`, promote betrayal, promote signal origins, promote lanes, or authorize live execution.

The append-only ledger is:

```text
logs/hammer_radar_forward/betrayal_source_emitter_refresh.ndjson
```

## Next Phases

- R217 should decompose aggregate betrayal candidates into direction/entry-mode candidates using local evidence only.
- R214 should resolve event outcomes only for future paper rows that are direction-specific and schema-complete.
