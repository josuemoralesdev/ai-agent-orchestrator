# R215 Betrayal Direction Split Resolver

R215 adds a paper-only direction split audit for betrayal aggregate candidates:

- `222m aggregate`
- `88m aggregate`
- `55m aggregate` when available

It reads R213, R212, R211, R210, local betrayal paper signals/outcomes, shadow outcomes, and full-spectrum capture seeds. It attempts to resolve direction split only when local schema explicitly identifies the original direction and inverse betrayal direction.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-direction-split-resolver
```

Append-only record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-direction-split-resolver \
  --record-resolver \
  --confirm-betrayal-direction-split-resolver "I CONFIRM BETRAYAL DIRECTION SPLIT RESOLVER RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected recording attempts return `BETRAYAL_DIRECTION_SPLIT_RESOLVER_REJECTED` and write no ledger row.

## Direction Rules

- `long` or `short` may be extracted from an explicit lane key.
- Lane-key direction alone is partial evidence only.
- Aggregate context remains unresolved.
- If `original_direction` is explicit, the inverse direction is the opposite direction.
- R96/R100 direction-entry-mode identities are the trusted local schema shape.
- Full-spectrum captures are never validated samples by themselves.
- No row can count as a validated sample in R215.

## Output

The JSON output includes:

- `input_summary`
- `direction_split_resolution_rows`
- `direction_split_summary`
- `direction_split_gap_report`
- `direction_split_recommendations`
- `direction_split_status`
- `safety`

Current R212 aggregate rows are expected to remain blocked unless local R100-style betrayal paper signals or true paper outcomes carry explicit original/inverse schema.

## Safety

R215 is audit-only and paper-only. It cannot write env/config/risk/lane state, cannot call Binance or network, cannot create order payloads, cannot place orders, cannot disable the kill switch, cannot promote betrayal or signal origins or lanes, cannot set any lane to `tiny_live`, and cannot authorize live execution.

The ledger is append-only and written only after exact confirmation:

```text
logs/hammer_radar_forward/betrayal_direction_split_resolver.ndjson
```

## Next Phases

- R214 should resolve paper-only event outcomes only for direction-specific rows.
- R216 should refresh betrayal source emission so future local rows carry explicit original and inverse direction fields.
