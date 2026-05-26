# R134 First Tiny-Live Order Payload Dry Authorization

R134 adds the first non-executing dry authorization packet for a future first tiny-live order payload review.

It is a diagnostic and audit layer over R126, R130, R131, R132, R125/R129 paper proof, the tiny-live risk contract, connector status, protective status, and R106/global gate evidence. It does not create an executable exchange payload.

## What R134 Adds

- `src/app/hammer_radar/operator/first_tiny_live_order_payload_dry_authorization.py`
- CLI mode: `first-tiny-live-order-payload-dry-authorization`
- Append-only review ledger:

```text
logs/hammer_radar_forward/first_tiny_live_order_payload_dry_authorizations.ndjson
```

The packet includes lane identity, candidate identity, risk contract hash, paper proof reference, R126/R130/R132 references, non-executable entry intent, risk-contract-referenced size policy, non-executable protective intent, kill-switch policy, and a dry authorization hash.

## What R134 Does Not Add

R134 does not:

- place real orders
- create Binance order payloads
- create protective order payloads
- create signed requests
- call Binance order endpoints
- call Binance test-order endpoints
- call account, balance, funding, or position endpoints
- mutate env files
- mutate lane config
- enable global live flags
- bypass R106/global gates
- implement live adapter behavior
- create a live order endpoint

## Why R134 Comes After R132

R132 is the final live adapter boundary review before any dry order-payload authorization. R134 consumes that boundary review and remains blocked unless the R132 status is ready, the review is complete, and the R132 blocker list is clear.

R132 can safely report that its review completed while still showing boundary blockers. R134 treats those blockers as readiness blockers and will not report `DRY_AUTHORIZATION_READY` while they remain.

## Non-Executable Packet

The R134 packet is intentionally not sendable to an exchange:

- `entry_intent.direct_exchange_payload` is `null`
- `entry_intent.signed_request` is `null`
- `protective_intent.direct_exchange_payload` is `null`
- `protective_intent.signed_request` is `null`
- `size_policy.direct_live_quantity` is `null`

The packet may describe intent boundaries such as side, order type intent, max daily loss, max daily trades, and protective requirements. It cannot be used as a Binance request.

## Forbidden Fields

R134 packets must not include:

- credential values
- signatures
- signed params
- query strings
- `recvWindow`
- timestamps
- Binance endpoints
- base URLs
- direct live quantity
- executable order payload material
- network targets

Credential state is reported only as local boolean prerequisite status outside the packet.

## Prerequisites

`DRY_AUTHORIZATION_READY` is possible only when all of these are true:

- selected lane exists
- lane mode is `tiny_live`
- R126 tiny-live execution gate is `TINY_LIVE_EXECUTION_READY`
- R130 tiny-live authorization is recorded or ready
- R131 kill-switch rehearsal is `KILL_SWITCH_REHEARSAL_READY`
- R132 live adapter boundary review is ready, complete, and clear
- recent R125/R129 autonomous paper proof exists
- tiny-live risk contract is valid and includes max loss plus protective policy
- protective orders are ready, or represented as a non-executing dry requirement
- credential presence is verified as booleans only
- R106/global gate is `FIRST_LIVE_ACTIVATION_READY`
- safety fields remain false and paper/live separation remains intact
- no executable payload, signed request, or network use is created

In the current default repo state, R134 is expected to return `DRY_AUTHORIZATION_BLOCKED` because the selected lane is still `armed_dry_run`, R132 boundary blockers remain, credentials are absent, protective orders are preview-only, and R106/global readiness remains blocked.

## Confirmation Phrase

Recording a dry authorization review requires the exact phrase:

```text
I CONFIRM FIRST TINY LIVE DRY AUTHORIZATION ONLY; NO ORDER; NO BINANCE CALL.
```

This phrase records R134 dry authorization review evidence only. It does not authorize order placement.

## CLI

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  first-tiny-live-order-payload-dry-authorization \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618"
```

Rejected recording example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  first-tiny-live-order-payload-dry-authorization \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --record-dry-authorization \
  --confirm-dry-authorization "wrong"
```

Confirmed recording writes only the append-only R134 ledger when prerequisites and safety checks are clear. It still does not create payloads, sign requests, call Binance, or place orders.

## Safety Constraints

R134 always reports:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `signed_request_created=false`
- `network_allowed=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `secrets_shown=false`
- `paper_live_separation_intact=true`
- `env_mutated=false`
- `config_written=false`
- `global_live_flags_changed=false`

## R135 Preparation

R134 prepares R135 by producing a dry authorization packet that describes intent boundaries without executable exchange material. R135 may rehearse live adapter function boundaries against that packet, but it must still avoid real orders, Binance order endpoints, signed requests, and network use.
