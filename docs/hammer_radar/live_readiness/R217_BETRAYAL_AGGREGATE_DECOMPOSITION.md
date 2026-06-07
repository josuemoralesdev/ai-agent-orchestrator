# R217 Betrayal Aggregate Decomposition

R217 adds a paper-only aggregate decomposition audit for betrayal candidates:

- `222m aggregate`
- `88m aggregate`
- `55m aggregate` when local evidence exists

It reads R216 source emitter refresh, R215 direction split resolver, R212 event tracker, R210 true inverse refresh, local shadow/true-paper/paper-signal ledgers, and full-spectrum capture seeds. It groups evidence by timeframe, explicit original/inverse direction, entry mode, source identity, and source family.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-aggregate-decomposition
```

Append-only record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-aggregate-decomposition \
  --record-decomposition \
  --confirm-betrayal-aggregate-decomposition "I CONFIRM BETRAYAL AGGREGATE DECOMPOSITION RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Wrong confirmations return `BETRAYAL_AGGREGATE_DECOMPOSITION_REJECTED` and write no ledger row.

## Decomposition Rules

A row is ready for v2 source-row preview only when local evidence has:

- known timeframe
- explicit `original_direction`
- explicit opposite `inverse_direction`
- explicit `entry_mode`
- explicit `source_identity` or `source_signal_id`
- explicit `signal_timestamp`
- `paper_only=true`
- `live_authorized=false`

Rows with explicit original/inverse direction but missing entry mode or source identity remain partial. Aggregate-only rows, lane-direction-only rows, no-timestamp rows, and no-identity rows remain blocked.

R217 does not infer entry mode from default ladder mode and does not infer source identity from a candidate label.

## Output

The JSON output includes:

- `input_summary`
- `decomposition_rows`
- `decomposition_summary`
- `v2_source_rows_preview`
- `decomposition_gap_report`
- `decomposition_recommendations`
- `decomposition_status`
- `safety`

`v2_source_rows_preview` is preview-only and includes schema-complete rows only. A preview row does not append a source row and does not count as a validated sample.

## Safety

R217 is decomposition audit only. It cannot call Binance or network, create order payloads, place orders, transfer, withdraw, write env/config/risk/lane/registry/scoring/matrix state, disable the kill switch, set any lane `tiny_live`, promote betrayal or signal origins or lanes, infer tiny-live readiness, or authorize live execution.

The append-only ledger is:

```text
logs/hammer_radar_forward/betrayal_aggregate_decomposition.ndjson
```

## Next Phases

- R218 should append v2 betrayal source rows only when R217 has schema-complete ready rows.
- R214 should resolve event outcomes only for appended paper-only, schema-complete direction-specific source rows.
