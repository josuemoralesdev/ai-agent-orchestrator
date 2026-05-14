# R85 Exact Operator Approval + Non-Executable Ticket Builder

## Purpose

R85 adds a local tiny-live ticket builder for operator review. It binds the exact R84.1 candidate, risk contract, local funding metadata, live env lock state, and exact approval requirement into a deterministic non-executable ticket.

The current candidate is:

```text
normal|BTCUSDT|13m|long|ladder_close_50_618
```

R85 does not place orders, create signed payloads, call Binance, check account balances, expose secrets, modify env files, restart services, or enable live execution.

## Why R85 Follows R84.1

R84.1 moved the top candidate from missing risk/funding config to:

```text
risk_contract_status=RISK_CONTRACT_VALID_FOR_PREFLIGHT
funding_status=FUNDING_CONFIG_PRESENT
funding_check_mode=LOCAL_CONFIG_ONLY_NO_NETWORK
final_preflight_status=BLOCKED_BY_MISSING_OPERATOR_APPROVAL
```

R85 creates the review artifact required before any later live arming checklist can be considered. It records review intent only.

## Risk Contract Hash

R85 computes:

```text
risk_contract_hash=sha256(stable_json(risk_contract_snapshot))
```

Stable JSON uses sorted keys and compact separators so the same contract produces the same hash.

The hash binds the approval phrase to the exact risk contract snapshot reviewed by the operator.

## Exact Approval Phrase

R85 generates an exact phrase:

```text
APPROVE_TINY_LIVE_REVIEW normal|BTCUSDT|13m|long|ladder_close_50_618 <risk_contract_hash>
```

Missing approval returns:

```text
MISSING_OPERATOR_APPROVAL
TICKET_APPROVAL_REQUIRED
```

A wrong phrase returns:

```text
OPERATOR_APPROVAL_INVALID
```

An exact phrase may record:

```text
OPERATOR_APPROVAL_RECORDED_FOR_REVIEW
TICKET_CREATED_FOR_OPERATOR_REVIEW
```

That is still review-only. It does not approve exchange execution.

## Dry-Run And Write Behavior

Default behavior is dry-run/no-write.

```text
dry_run=true
write=false
```

Only `dry_run=false` and `write=true` may append a ticket to:

```text
logs/hammer_radar_forward/tiny_live_tickets.ndjson
```

Tickets are append-only local NDJSON records. They are not order payloads.

## Ticket Guarantees

Every R85 ticket keeps:

```text
review_only=true
executable=false
order_type=not_created
order_payload_created=false
execution_attempted=false
network_allowed=false
secrets_shown=false
```

Even exact approval phrase matches remain non-executable.

## API

Build ticket dry-run:

```text
POST /live-arming/ticket/build
{
  "dry_run": true,
  "write": false
}
```

Read tickets:

```text
GET /live-arming/tickets
```

## CLI

Dry-run ticket:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-ticket
```

Write a non-executable review ticket:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-ticket \
  --write \
  --approval-phrase "APPROVE_TINY_LIVE_REVIEW normal|BTCUSDT|13m|long|ladder_close_50_618 <risk_contract_hash>"
```

## No-Live Guarantees

R85 preserves:

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
```

R85 does not create live orders, signed order payloads, executable tickets, Binance requests, automatic approval, or real balance checks.

## Smoke Commands

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-ticket
```

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  live-arming-preflight
```

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract
```

API when the local service is already running:

```text
curl -s -X POST http://127.0.0.1:8015/live-arming/ticket/build \
  -H 'Content-Type: application/json' \
  -d '{"dry_run":true,"write":false}' | jq '
{
  status,
  phase,
  execution_mode,
  ticket_status,
  candidate_id,
  risk_contract_hash,
  approval_status,
  approval_phrase_required,
  executable,
  review_only,
  order_placed,
  real_order_placed,
  execution_attempted,
  order_payload_created,
  network_allowed,
  secrets_shown
}'
```

## Next Phase Recommendation

R86 adds Live Env Arming Checklist + Manual Funding Confirmation. R87 adds Live Env Toggle Design + Execution Boundary Review to document which future phase may request env changes and which execution boundaries still prevent order creation.
