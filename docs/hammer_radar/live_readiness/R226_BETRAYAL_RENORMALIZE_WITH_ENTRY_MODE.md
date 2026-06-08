# R226 Betrayal Renormalize With Entry Mode

R226 adds a paper-only renormalization preview over existing betrayal evidence. It reads R225 entry-mode evidence, R224A source-identity evidence, R223 normalizer rows, and the R218/R219 registry contract, then previews `betrayal_source_emitter_v2` rows only when local evidence supplies the required fields.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-renormalize-with-entry-mode
```

Record audit only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-renormalize-with-entry-mode \
  --record-renormalization \
  --confirm-betrayal-renormalize-with-entry-mode "I CONFIRM BETRAYAL RENORMALIZE WITH ENTRY MODE RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Behavior

- Joins evidence by stable identifiers: source signal id, source identity, emitted id, lane key, or candidate/timeframe/timestamp.
- Does not propagate entry mode from candidate/timeframe alone.
- Does not fabricate common ladder mode, source identity, direction, emitted id, or lane key.
- Marks `resolver_ready_preview=true` only when all registry-required `betrayal_source_emitter_v2` fields are present and `emitted_direction == inverse_direction`.
- Keeps rows `paper_only=true`, `live_authorized=false`, and `promotion_allowed=false`.
- Records only `logs/hammer_radar_forward/betrayal_renormalize_with_entry_mode.ndjson` when confirmed.

## Safety

R226 does not append normalized source rows, write env/config/risk/lane files, call Binance/network, create order payloads, place orders, transfer, withdraw, disable the kill switch, promote betrayal, promote signal origins or lanes, infer tiny-live readiness, or authorize live execution.

## Latest Local Preview

The current local preview reports:

- `resolver_ready_preview_rows=0`
- `renormalization_status=RENORMALIZATION_ENTRY_MODE_STILL_BLOCKED`

R224 append remains blocked unless a future R226 preview reports `resolver_ready_preview_rows > 0`.
