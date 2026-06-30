# Hammer Operator Model

## Operator Role

The Hammer operator is the human authority over trading risk. Hammer may observe, rank, prepare, and explain. The operator decides whether to watch, reject, paper-test, record review intent, record exact confirmations, arm dry-run lanes, or proceed through future explicit live gates.

## Operator Workflow

Hammer's operator workflow is staged:

1. Observe signals and candidates.
2. Review strategy evidence, lane status, source-chain health, and blockers.
3. Build non-executable tickets or review packets.
4. Record explicit operator decisions.
5. Run paper or dry-run paths before live.
6. Recheck readiness and safety envelopes.
7. Require exact hashes, exact phrases, and final approval intent for live review.
8. Keep execution blocked unless all execution gates pass.

## Operator Surfaces

Hammer exposes operator state through the local Approval API, inspect CLI, Telegram/operator command bridge, readiness endpoints, live-arming endpoints, lane cockpit, final console, and paper refresh surfaces.

Important endpoint groups include:

- `/readiness`
- `/trade-ticket`
- `/paper-executions`
- `/live-safety`
- `/live-arming/*`
- `/live/*`
- `/binance-live/*`
- `/operator/*`
- `/telegram/*`
- `/strategy-performance/*`
- `/tiny-live/*`

These surfaces are operator review and control surfaces. They are not generic public APIs.

## Approval Gates

Hammer uses multiple approval concepts:

- paper ticket approval
- tiny-live review ticket approval
- human confirmation records
- final approval intent
- Telegram approval challenge and reply
- first-live activation gate
- protected execution gate

The language is intentionally narrow. A recorded approval may mean "accepted intent only" or "review record persisted." It does not necessarily mean live order permission.

## Execution Gates

Execution gates are stricter than approval gates. They compose final preflight, risk contracts, live flags, kill switch, credentials presence, protective readiness, dry-run proof, paper/live separation, exact operator confirmation, and idempotency.

The current model keeps live execution disabled by default. The first-live activation gate and first-live execution gate both preserve `order_placed=false` and `real_order_placed=false` unless a future explicitly approved phase changes the boundary.

## Lane System

Hammer lanes are exact strategy/execution identities:

```text
SYMBOL|timeframe|direction|entry_mode
```

Examples:

```text
BTCUSDT|13m|long|ladder_close_50_618
BTCUSDT|44m|long|ladder_close_50_618
BTCUSDT|8m|short|ladder_close_50_618
```

Lane controls express operator intent and risk context. Lane modes include disabled, paper, armed dry-run, and tiny-live. A tiny-live lane still requires global gates, risk contracts, protective readiness, and operator authority.

## Operator Authority Preservation

Hammer preserves operator authority by requiring exactness:

- exact lane key
- exact candidate id
- exact risk contract hash
- exact packet hash
- exact approval phrases
- explicit manual outcome records
- explicit arming/disarming commands
- explicit dry-run/live distinction

The machine may recommend a next move, but it must keep blockers visible and must not silently promote strategy output into live execution.

## Operator Memory

Operator memory is durable and local:

- decision records
- manual outcomes
- paper execution records
- approval intents
- human confirmations
- live attempt records
- review packets
- readiness snapshots

This memory gives the operator an audit trail and gives Hammer enough context to enforce daily stops, avoid repeated candidate reuse, validate hash chains, and explain why a lane is ready or blocked.
