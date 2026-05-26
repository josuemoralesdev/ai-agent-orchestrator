# R135 Live Adapter Execution Rehearsal

R135 adds a non-executing rehearsal layer between the R134 dry authorization packet and the future live adapter execution boundary.

It answers which adapter functions would be involved later, which functions remain forbidden now, which stop conditions block execution, which protective order requirements remain unresolved, and which future phases must happen before any real tiny-live order.

## What R135 Adds

- `src/app/hammer_radar/operator/live_adapter_execution_rehearsal.py`
- CLI mode: `live-adapter-execution-rehearsal`
- Append-only rehearsal ledger:

```text
logs/hammer_radar_forward/live_adapter_execution_rehearsals.ndjson
```

The rehearsal output includes R134 dry authorization status, a static adapter function map, payload/network/credential/protective/kill-switch/global-gate boundaries, stop conditions, future execution adapter requirements, and safety flags.

## What R135 Does Not Add

R135 does not:

- place real orders
- create executable Binance order payloads
- create protective order payloads
- create signed requests
- call Binance order endpoints
- call Binance test-order endpoints
- call protective order endpoints
- call account, balance, funding, or position endpoints
- mutate env files
- mutate lane config
- enable global live flags
- bypass R106/global gates
- implement live adapter behavior
- create a live order endpoint

## How R135 Uses R134 And R132

R135 reuses R134 as the only dry authorization packet source. The packet must remain non-executable: direct exchange payloads and signed requests must stay `null`.

R135 reuses R132 as the adapter boundary source for connector mode, protective status, credential booleans, kill-switch behavior, and global gate blockers. R132 remains review-only and R135 does not turn it into execution authority.

## Forbidden Adapter Functions

R135 statically maps connector functions in `binance_futures_connector.py` without calling forbidden functions.

Classifications:

- `READ_ONLY_STATUS_OK`: status and path helpers such as `build_connector_status` and `build_protective_status`.
- `PAYLOAD_PREVIEW_FORBIDDEN_IN_R135`: `preview_payload`, `protective_preview`, and internal payload preview builders.
- `SIGNING_FORBIDDEN`: `sign_query`, signed request builders, and canonical query material builders.
- `NETWORK_FORBIDDEN`: test-order, live-order, and protective network send paths.
- `EXECUTION_FORBIDDEN`: live execution and adapter submission methods.

## Stop Conditions

R135 blocks future execution when any of these are true:

- R134 dry authorization is not ready and non-executable.
- A forbidden payload, signing, network, or execution function would be called.
- Any direct exchange payload, order payload, executable payload, or signed request exists.
- Protective stop/take-profit policy is unresolved.
- Credential presence is missing or would expose values.
- Network, order, test-order, protective, account, or balance endpoints would be used.
- R131 kill-switch rehearsal does not prove global kill, lane disable, and rollback blocks.
- R106/global gate, final preflight, or live env boundary is not ready.
- Any safety flag flips true or paper/live separation is not intact.

## Protective Rehearsal Requirements

R135 requires protective orders to remain a blocker until stop and take-profit policy are explicitly ready. Protective payload creation is forbidden in R135.

R136 must define the protective stop/take-profit dry policy before any adapter implementation plan.

## Credential Handling

Credentials are represented only as booleans:

- `api_key_present`
- `api_secret_present`

R135 never prints credential values, signatures, auth headers, query strings, or env contents.

## Why No Network, Signing, Or Order Occurs

R135 only composes existing review outputs and statically inspects connector function names. It does not call connector preview, signing, submit, or execute functions.

Safety output always keeps:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `signed_request_created=false`
- `network_allowed=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `protective_order_endpoint_called=false`
- `secrets_shown=false`
- `paper_live_separation_intact=true`
- `env_mutated=false`
- `config_written=false`
- `global_live_flags_changed=false`

## Confirmation Phrase

Recording a rehearsal requires the exact phrase:

```text
I CONFIRM LIVE ADAPTER REHEARSAL ONLY; NO ORDER; NO BINANCE CALL.
```

This records rehearsal only. It does not authorize order placement.

## CLI

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  live-adapter-execution-rehearsal \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618"
```

Rejected recording example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  live-adapter-execution-rehearsal \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --record-rehearsal \
  --confirm-adapter-rehearsal "wrong"
```

Confirmed recording writes only the append-only R135 rehearsal ledger when the exact phrase is supplied and safety remains false.

## Ledger

Confirmed rehearsals write to:

```text
logs/hammer_radar_forward/live_adapter_execution_rehearsals.ndjson
```

Each record includes event type, rehearsal id, timestamp, lane key, status, rehearsal areas, forbidden function map, stop conditions, future execution adapter requirements, main blockers, safety flags, and source surfaces used.

## Next Phases

- R136 Protective Order Dry Policy Review: define protective stop/take-profit dry policy with no Binance calls, no signed requests, and no real orders.
- R137 First Tiny-Live Execution Adapter Implementation Plan: plan exact future adapter behavior, signing boundary, network boundary, rollback, and tests.
- R138 First Tiny-Live Execution Final Authorization: final current-turn authorization gate before any real tiny-live execution attempt.
