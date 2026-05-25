# R130 First Tiny-Live Autonomous Lane Authorization

Phase: R130

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## What R130 Adds

R130 adds a non-executing authorization-intent layer for one configured autonomous lane:

```text
src/app/hammer_radar/operator/first_tiny_live_autonomous_lane_authorization.py
```

It lets the operator record that a specific lane is authorized for future tiny-live autonomous review after the existing lane, paper-proof, risk-contract, and R126 gate surfaces have been checked.

The append-only ledger is:

```text
logs/hammer_radar_forward/first_tiny_live_autonomous_lane_authorizations.ndjson
```

## What R130 Does Not Add

R130 does not:

- place orders
- create Binance order payloads
- call Binance order endpoints
- send signed requests
- mutate env files
- enable global live execution
- bypass R106 or global gates
- weaken tiny-live eligibility
- implement live adapter behavior
- create a live order endpoint
- install or start services

The authorization record is operator intent only. It is not order execution and it is not live adapter permission.

## How R130 Uses R126 And R129

R130 reuses:

- R122 lane controls to prove the lane exists and carries max daily trades, max daily loss, cooldown, freshness, and protective-order requirements.
- R126 first tiny-live lane execution gate status and readiness hash.
- R125 paper lane records and R129 paper integration records as paper proof.
- Tiny-live risk contracts for max loss, protective stop, take-profit, and contract hash.
- R124 lane-command preview semantics for any requested `tiny_live` lane-mode change preview.

R130 blocks authorization if R126 is not `TINY_LIVE_EXECUTION_READY` for the lane, if paper proof is missing, or if risk/protective policy is missing.

## Confirmation Phrase

Recording authorization requires the exact phrase:

```text
I CONFIRM TINY LIVE LANE AUTHORIZATION ONLY; NO ORDER; NO BINANCE CALL.
```

This phrase authorizes only the append-only R130 authorization ledger record. It does not authorize any order, Binance call, live adapter behavior, or env/config change.

## Authorization Packet

The authorization packet is non-executable. It includes lane identity, requested mode, daily/cooldown/freshness policy, protective-order requirement, paper proof reference, R126 readiness hash, risk contract hash, authorization hash, and the future execution confirmation placeholder.

It must not include API keys, secrets, signed payloads, exchange order payloads, direct Binance endpoints, or direct live quantity.

## Lane Mode Request Behavior

Preview is default. `--request-lane-mode-tiny-live` asks R130 to show the R124 lane-command preview for `tiny_live` mode.

R130 does not mutate `configs/hammer_radar/lane_controls.json`. If `--apply-lane-mode-change` is supplied, R130 blocks the config write and recommends using the R124 `lane-control-command` flow with R124's own exact config-change confirmation phrase.

This keeps lane authorization separate from lane config mutation.

## CLI

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  first-tiny-live-autonomous-lane-authorization \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618"
```

Rejected record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  first-tiny-live-autonomous-lane-authorization \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --record-authorization \
  --confirm-tiny-live-authorization "wrong"
```

Confirmed authorization record, only after prerequisites are ready:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  first-tiny-live-autonomous-lane-authorization \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --record-authorization \
  --confirm-tiny-live-authorization "I CONFIRM TINY LIVE LANE AUTHORIZATION ONLY; NO ORDER; NO BINANCE CALL."
```

Do not run the confirmed record command unless the operator intentionally wants to append the local R130 authorization ledger.

## Safety Constraints

R130 always reports:

```json
{"order_placed":false,"real_order_placed":false,"execution_attempted":false,"order_payload_created":false,"network_allowed":false,"secrets_shown":false,"paper_live_separation_intact":true,"env_mutated":false,"global_live_flags_changed":false}
```

Authorization recording is refused when the lane is unknown, the exact phrase is missing, paper proof is absent, R126 is blocked, risk contract is missing, protective policy is absent, paper/live separation is false, or any order/execution/network/secret safety flag is unsafe.

## How This Prepares Later Execution

R130 creates the auditable lane-level authorization layer needed before future dry authorization and live adapter review phases. Later phases still need separate kill-switch rehearsal, live adapter boundary review, and one-order dry authorization before any execution can be considered.

## Next Phases

- R131 live lane kill-switch rehearsal
- R132 live adapter boundary final review
- R133 lane control cockpit UI
- R134 first tiny-live order payload dry authorization
