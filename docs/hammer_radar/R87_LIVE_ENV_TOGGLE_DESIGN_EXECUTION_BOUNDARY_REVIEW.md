# R87 Live Env Toggle Design + Execution Boundary Review

## Purpose

R87 adds a read-only live-env boundary review surface. It reports which live toggles exist, what their current safe states are, which future phase could request changes, what must be true before live arming is considered, and which actions remain forbidden.

R87 does not place orders, sign payloads, call Binance, check account balances, modify env files, restart services, or enable live execution.

## Why R87 Follows R86

R86 added local manual funding and live-env checklist confirmations. R87 defines the boundary between those local confirmations and any future live environment arming.

Current candidate:

```text
normal|BTCUSDT|13m|long|ladder_close_50_618
```

Current risk hash:

```text
764df0c3cea3357416872be8d47e0f6189324cc8fbd0711dc5d1c8385ba114d8
```

R87 treats R83/R84/R85/R86 evidence as review context only. It does not convert any record into live execution permission.

## Live Toggle Design

R87 reviews these known non-secret toggles:

- `HAMMER_BINANCE_LIVE_ENABLED`
- `HAMMER_LIVE_EXECUTION_ENABLED`
- `HAMMER_ALLOW_LIVE_ORDERS`
- `HAMMER_GLOBAL_KILL_SWITCH`

Expected safe states:

```text
HAMMER_BINANCE_LIVE_ENABLED=false
HAMMER_LIVE_EXECUTION_ENABLED=false
HAMMER_ALLOW_LIVE_ORDERS=false
HAMMER_GLOBAL_KILL_SWITCH=true
```

Missing toggles are reported as `TOGGLE_NOT_FOUND` and do not expose secrets.

## Execution Boundary

R87 reports the execution boundary as intact only when these protections remain true:

- `EXECUTION_BOUNDARY_NO_ORDER_PAYLOAD`
- `EXECUTION_BOUNDARY_NO_NETWORK`
- `EXECUTION_BOUNDARY_NO_SIGNING`
- `EXECUTION_BOUNDARY_NO_BINANCE`
- `EXECUTION_BOUNDARY_REVIEW_ONLY`

The R87 surface keeps:

```text
order_payload_created=false
execution_attempted=false
network_allowed=false
secrets_shown=false
```

## Future Arming Requirements

Before any future live arming phase is even considered:

1. R83 top candidate must still support the exact candidate.
2. R84 risk contract must remain valid for preflight.
3. R85 non-executable ticket must exist with exact approval recorded for review.
4. R86 checklist must exist with exact manual phrases recorded for review.
5. Manual funding may be confirmed by operator, but is not a balance check.
6. Global kill switch must remain intentionally reviewed.
7. Any env change must happen only in a future explicit phase.
8. Any real exchange account balance check must be separate and explicitly approved.
9. Protective stop and take-profit must exist before any executable payload exists.
10. A future execution phase must still require final explicit approval.

## Forbidden Actions

R87 forbids:

- Binance calls
- account balance calls
- env mutation
- service restart
- order payload creation
- signing
- execution attempt
- automatic approval
- kill-switch disablement

## Optional Report

Default behavior is dry-run/no-write.

```text
dry_run=true
write=false
```

Only `dry_run=false` and `write=true` may write a local JSON report:

```text
logs/hammer_radar_forward/live_env_boundary_review.json
```

That report is documentation only and does not modify env or execution state.

## Smoke Commands

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  live-env-boundary-review
```

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  live-env-checklist
```

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-ticket
```

## Next Phase Recommendation

R88 adds Final Human Approval Record + Review Packet. It bundles R83 through R87 evidence into one final non-executable operator review artifact before any later human confirmation persistence phase.
