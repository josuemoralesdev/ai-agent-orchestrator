# R136 Protective Order Dry Policy Review

R136 adds a non-executing protective order policy review before any future tiny-live lane execution can be authorized.

It defines the stop-loss and take-profit policy boundary for the selected first tiny-live lane, derives references from the lane, tiny-live risk contract, and recent paper proof where available, and records only review evidence after an exact confirmation phrase.

## What R136 Adds

- `src/app/hammer_radar/operator/protective_order_dry_policy_review.py`
- inspect CLI mode: `protective-order-dry-policy-review`
- append-only review ledger:

```text
logs/hammer_radar_forward/protective_order_dry_policy_reviews.ndjson
```

The review returns policy areas, a non-executing protective policy packet, a forbidden payload map, future dry-preview requirements, blockers, next actions, and safety flags.

## What R136 Does Not Add

R136 does not:

- place orders
- create executable stop-loss or take-profit payloads
- create signed requests
- call Binance
- call Binance test-order endpoints
- call protective order endpoints
- call connector protective preview or submit helpers
- mutate env files
- mutate lane config
- enable global live flags
- bypass R106 or global gates
- implement live adapter behavior

## Why Protective Policy Blocks Live Readiness

R132 showed protective orders are disabled or `PREVIEW_ONLY`. R134 dry authorization stays blocked until protective stop and take-profit readiness are explicit. R135 rehearsed the adapter boundary but kept protective policy unresolved.

R136 makes that blocker precise: every live entry must have required stop-loss and take-profit policy, but this phase may express only non-executable intent.

## Stop-Loss Policy Boundary

The stop-loss policy reports:

- whether stop-loss is required by the risk contract
- whether a numeric stop reference is available
- whether the reference came from candidate, paper proof, risk contract, or is unknown
- `direct_exchange_payload=null`
- `signed_request=null`
- executable payload and signed request flags remain false

## Take-Profit Policy Boundary

The take-profit policy reports the same non-executing fields:

- requirement status
- numeric reference availability
- source
- `direct_exchange_payload=null`
- `signed_request=null`
- executable payload and signed request flags remain false

## Risk Contract Boundary

R136 reuses the tiny-live risk contract. It reports:

- contract presence
- risk contract hash
- max loss cap
- max daily loss/trades when present
- protective stop requirement
- take-profit requirement
- `direct_live_quantity=null`

## Paper Proof Boundary

R136 reuses R125/R129 paper proof records. The review checks:

- recent paper proof exists
- proof has entry, stop, and take-profit references
- proof lane matches the selected lane
- proof candidate matches the current candidate when available

Missing paper proof or missing stop/take-profit references remain blockers.

## Connector Protective Boundary

R136 reuses connector protective status only through read-only status builders. It reports:

- connector mode
- protective orders enabled
- protective order mode: `PREVIEW_ONLY`, `READY`, or `UNKNOWN`
- no protective endpoint called

`PREVIEW_ONLY`, disabled, or unknown protective state blocks dry payload-preview readiness.

## Forbidden Payload Map

R136 marks these functions and paths forbidden:

- `protective_preview`
- `submit_protective_test`
- signed protective request builders
- protective network clients
- protective adapter send functions

The review packet cannot include API keys, API secrets, signatures, query strings, Binance endpoints, timestamps, `recvWindow`, network targets, direct live quantity, or direct exchange payloads.

## Confirmation Phrase

Confirmed review recording requires the exact phrase:

```text
I CONFIRM PROTECTIVE ORDER DRY POLICY REVIEW ONLY; NO ORDER; NO BINANCE CALL.
```

This records protective policy review evidence only. It does not authorize order placement.

## CLI

Preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  protective-order-dry-policy-review \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618"
```

Rejected record attempt:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  protective-order-dry-policy-review \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --record-review \
  --confirm-protective-review "wrong"
```

Confirmed recording writes only the append-only R136 review ledger when the exact phrase is supplied and all policy blockers are clear.

## Future Dry Payload Preview

R136 prepares R137/R138 by defining what must be true before a future abstract dry preview may be considered:

- R136 review recorded and ready
- stop-loss reference present
- take-profit reference present
- protective orders required by lane, risk contract, and connector
- connector protective mode advanced by a future approved phase
- preview remains abstract and non-executable
- direct exchange payloads, signed requests, endpoints, timestamps, `recvWindow`, signatures, and network targets remain absent

R137 may define the future protective payload dry-preview boundary, but it still must not create real Binance payloads, signed requests, or network calls.
