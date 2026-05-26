# R137 Protective Payload Dry Preview Boundary

R137 adds the protective payload dry preview boundary layer after R136. It defines what a future non-executable stop-loss and take-profit preview packet would look like while proving no executable protective order payload, signed request, Binance endpoint call, network request, env mutation, config mutation, or order placement occurs.

## What R137 Adds

- `src/app/hammer_radar/operator/protective_payload_dry_preview_boundary.py`
- inspect CLI mode: `protective-payload-dry-preview-boundary`
- append-only preview ledger:

```text
logs/hammer_radar_forward/protective_payload_dry_preview_boundaries.ndjson
```

The output includes preview areas, an abstract protective preview packet, a forbidden field report, future requirements, blockers, next actions, safety flags, and source surfaces used.

## What R137 Does Not Add

R137 does not:

- place orders
- create executable stop-loss or take-profit payloads
- create signed requests
- call Binance
- call Binance test-order endpoints
- call protective order endpoints
- call connector `protective_preview`, submit, signing, or send helpers
- mutate env files
- mutate lane config
- enable global live flags
- bypass R106 or global gates
- implement live adapter behavior

## How R137 Uses R136

R136 remains the source of truth for protective stop-loss and take-profit policy. R137 checks that a ready R136 policy exists, a ready R136 record is present, the protective policy hash is available, stop/take-profit references exist, and the R136 packet is non-executable.

If R136 is missing, blocked, unrecorded, or lacks stop/take-profit references, R137 returns `PROTECTIVE_PAYLOAD_BLOCKED`.

## Non-Executable Preview Packet

The R137 packet type is:

```text
PROTECTIVE_PAYLOAD_DRY_PREVIEW_BOUNDARY
```

It includes abstract intent only:

- lane key, symbol, timeframe, direction, entry mode
- R136 protective policy hash
- entry reference when available
- stop-loss preview intent
- take-profit preview intent
- risk validation summary
- forbidden fields present list
- protective preview hash

The stop-loss and take-profit previews force these fields to `null`:

- `direct_exchange_payload`
- `signed_request`
- `endpoint`
- `quantity`

## Forbidden Fields

The forbidden field report checks for exchange-submittable or signing material:

- symbol/side/type/quantity payload that can be sent directly
- timestamp
- `recvWindow`
- signature
- API key
- endpoint URL
- signed material
- network target

Safe previews report an empty `forbidden_fields_present` list.

## Stop-Loss Preview Boundary

The stop-loss preview reports:

- whether the stop is required by R136
- numeric stop reference
- reference source
- side intent derived from lane direction
- order type intent
- side/direction relation validation
- null direct exchange payload, signed request, endpoint, and quantity

## Take-Profit Preview Boundary

The take-profit preview mirrors the stop-loss boundary:

- whether take-profit is required
- numeric take-profit reference
- reference source
- side intent derived from lane direction
- order type intent
- null direct exchange payload, signed request, endpoint, and quantity

## Risk Validation Boundary

R137 checks entry, stop, and take-profit relations when references are available. For a long lane, stop must be below entry and take-profit must be above entry. For a short lane, stop must be above entry and take-profit must be below entry.

`direct_live_quantity` remains `null`.

## Connector Boundary

R137 may read connector/protective status through existing read-only status builders, but it does not call connector payload preview, signing, submit, protective endpoint, or network functions.

## Confirmation Phrase

Confirmed preview recording requires the exact phrase:

```text
I CONFIRM PROTECTIVE PAYLOAD DRY PREVIEW ONLY; NO ORDER; NO BINANCE CALL.
```

This records protective payload preview boundary evidence only. It does not authorize order placement.

## CLI

Preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  protective-payload-dry-preview-boundary \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618"
```

Rejected record attempt:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  protective-payload-dry-preview-boundary \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --record-preview \
  --confirm-protective-preview "wrong"
```

Confirmed recording writes only the append-only R137 preview ledger when the exact phrase is supplied and all R137 blockers are clear.

## How This Prepares R138/R139

R137 creates the abstract boundary needed before future work can rank or clear remaining blockers. R138 should produce a live-ready burn-down ordered by paper proof, tiny-live lane mode, authorization, protective readiness, credential presence, global gate, adapter readiness, and final confirmation. R139 or later may only consider any deeper dry-run adapter work after those blockers are cleared and an explicit future phase authorizes it.
