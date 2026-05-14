# R86 Live Env Arming Checklist + Manual Funding Confirmation

## Purpose

R86 adds a local, non-secret checklist layer for manual funding and live-env review confirmations. It follows the R85 non-executable ticket builder and records whether the operator has manually acknowledged the exact candidate, risk hash, funding limits, kill switch state, live execution lock, and no-network/no-order constraints.

R86 is checklist and confirmation only. It does not place orders, sign payloads, create executable exchange payloads, call Binance, check balances, modify env files, restart services, or enable live execution.

## Why R86 Follows R85

R85 created a review-only ticket for:

```text
normal|BTCUSDT|13m|long|ladder_close_50_618
```

with risk contract hash:

```text
764df0c3cea3357416872be8d47e0f6189324cc8fbd0711dc5d1c8385ba114d8
```

and approval phrase:

```text
APPROVE_TINY_LIVE_REVIEW normal|BTCUSDT|13m|long|ladder_close_50_618 764df0c3cea3357416872be8d47e0f6189324cc8fbd0711dc5d1c8385ba114d8
```

R86 adds the next local review layer: manual funding and live-env checklist confirmations.

## Required Phrases

R86 requires deterministic phrases so accidental text cannot pass.

Manual funding:

```text
CONFIRM_MANUAL_FUNDING BTCUSDT MAX_MARGIN_44 MAX_LOSS_4.44 NO_BALANCE_CHECK
```

Live env review:

```text
CONFIRM_LIVE_ENV_REVIEW_ONLY KILL_SWITCH_ON LIVE_EXEC_DISABLED NO_ORDER
```

Max loss:

```text
ACK_MAX_LOSS_4.44_USDT
```

Exact candidate and risk hash:

```text
ACK_TINY_LIVE_CANDIDATE normal|BTCUSDT|13m|long|ladder_close_50_618 764df0c3cea3357416872be8d47e0f6189324cc8fbd0711dc5d1c8385ba114d8
```

## Manual Funding Limitation

Manual funding confirmation is not account-balance verification. R86 records that the operator says funding is available, but it does not call Binance account or balance endpoints.

The funding status remains local-only:

```text
account_balance_checked=false
account_balance_source=not_checked_no_network
network_allowed=false
```

## Dry-Run And Write Behavior

Default behavior is dry-run/no-write:

```text
dry_run=true
write=false
```

Only `dry_run=false` and `write=true` with all exact phrases may append a local checklist record to:

```text
logs/hammer_radar_forward/live_env_arming_checklists.ndjson
```

Checklist records are local review records, not execution payloads.

## Checklist Statuses

- `CHECKLIST_REQUIRED`
- `CHECKLIST_DRY_RUN_ONLY`
- `CHECKLIST_RECORDED_FOR_REVIEW`
- `CHECKLIST_BLOCKED_BY_MISSING_CONFIRMATIONS`
- `CHECKLIST_INVALID_CONFIRMATION`
- `CHECKLIST_EXPIRED`
- `CHECKLIST_NON_EXECUTABLE_REVIEW_ONLY`

## No-Live Guarantees

R86 preserves:

```text
live_execution_enabled=false
allow_live_orders=false
global_kill_switch=true
order_placed=false
real_order_placed=false
execution_attempted=false
order_payload_created=false
network_allowed=false
secrets_shown=false
env_modified=false
executable=false
review_only=true
```

R86 does not modify env files, create executable tickets, or convert manual confirmations into live authorization.

## Smoke Commands

Checklist dry-run:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  live-env-checklist
```

R85 ticket:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-ticket
```

R84 preflight:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  live-arming-preflight
```

API when the local service is already running:

```text
curl -s -X POST http://127.0.0.1:8015/live-arming/checklist/confirm \
  -H 'Content-Type: application/json' \
  -d '{"dry_run":true,"write":false}' | jq '
{
  status,
  phase,
  execution_mode,
  checklist_status,
  candidate_id,
  risk_contract_hash,
  manual_funding_status,
  live_env_arming_status,
  required_phrases,
  executable,
  review_only,
  checklist_written,
  order_placed,
  real_order_placed,
  execution_attempted,
  order_payload_created,
  network_allowed,
  secrets_shown
}'
```

## Next Phase Recommendation

R87 should add Live Env Toggle Design + Execution Boundary Review. It should define the exact boundary between local confirmations and any future env arming without enabling live execution unless a later phase explicitly authorizes it.
