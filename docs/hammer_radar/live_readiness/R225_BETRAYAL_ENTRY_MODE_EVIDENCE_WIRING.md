# R225 Betrayal Entry Mode Evidence Wiring

R225 adds a paper-only entry-mode evidence wiring layer for betrayal source
surfaces. It reads the R224A source identity evidence collector, R223
normalizer, R218 strategy evidence registry, R219 betrayal registry wiring,
R217 aggregate decomposition, R216 source emitter refresh, direction split,
event tracker, and full-spectrum capture records.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-entry-mode-evidence-wiring
```

Record the wiring audit only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-entry-mode-evidence-wiring \
  --record-wiring \
  --confirm-betrayal-entry-mode-evidence-wiring "I CONFIRM BETRAYAL ENTRY MODE EVIDENCE WIRING RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Scope

- Validates `entry_mode` only when it is explicit, parseable from `lane_key`,
  parseable from source signal/capture id, or emitted under a registry-backed
  contract.
- Rejects missing, unknown, `entry_unknown`, registry-missing, common-default,
  candidate-label, and timeframe-only inference.
- Produces a propagation contract for future full-spectrum capture, betrayal
  source emitter v2, event tracker, aggregate decomposition, and direction split
  rows.
- Leaves every row `paper_only=true`, `live_authorized=false`, and
  `can_feed_resolver_ready_preview=false`.

## Ledger

`logs/hammer_radar_forward/betrayal_entry_mode_evidence_wiring.ndjson`

The ledger is append-only and written only by the exact R225 confirmation
phrase.

## Safety

R225 does not append normalized source rows, write configs, mutate env files,
call Binance/network, create payloads, place orders, disable the kill switch,
promote betrayal, promote signal origins, promote lanes, or authorize live
execution.

R224 append remains blocked while R224A reports
`resolver_ready_preview_rows=0`. R226 should rerun paper-only normalization
using this entry-mode contract and produce resolver-ready previews only when all
registry-required fields exist.
