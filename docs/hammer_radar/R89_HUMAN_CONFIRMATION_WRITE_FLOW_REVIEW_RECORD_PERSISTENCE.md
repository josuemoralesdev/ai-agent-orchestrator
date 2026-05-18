# R89 Human Confirmation Write Flow + Review Record Persistence

## Purpose

R89 adds a local, durable, non-executable human confirmation ledger for the exact BTCUSDT tiny-live review chain.

It follows R88 by taking the final human review packet and the prior R85/R86 required phrases, then allowing exact human confirmations to be persisted as local review records only.

R89 does not place orders, sign payloads, create executable exchange payloads, call Binance, check balances, modify env files, restart services, disable the kill switch, or enable live execution.

## Exact Candidate And Hashes

Candidate:

```text
normal|BTCUSDT|13m|long|ladder_close_50_618
```

Risk contract hash:

```text
764df0c3cea3357416872be8d47e0f6189324cc8fbd0711dc5d1c8385ba114d8
```

R88 packet hash:

```text
b82fac02035b4a1b784548823c42f15c3082b01329cbcd6f72a5ac2000669625
```

## Required Phrases

R85 ticket review approval:

```text
APPROVE_TINY_LIVE_REVIEW normal|BTCUSDT|13m|long|ladder_close_50_618 764df0c3cea3357416872be8d47e0f6189324cc8fbd0711dc5d1c8385ba114d8
```

R86 checklist confirmations:

```text
CONFIRM_MANUAL_FUNDING BTCUSDT MAX_MARGIN_44 MAX_LOSS_4.44 NO_BALANCE_CHECK
CONFIRM_LIVE_ENV_REVIEW_ONLY KILL_SWITCH_ON LIVE_EXEC_DISABLED NO_ORDER
ACK_MAX_LOSS_4.44_USDT
ACK_TINY_LIVE_CANDIDATE normal|BTCUSDT|13m|long|ladder_close_50_618 764df0c3cea3357416872be8d47e0f6189324cc8fbd0711dc5d1c8385ba114d8
```

R88 final human review approval:

```text
FINAL_REVIEW_ACK normal|BTCUSDT|13m|long|ladder_close_50_618 764df0c3cea3357416872be8d47e0f6189324cc8fbd0711dc5d1c8385ba114d8 b82fac02035b4a1b784548823c42f15c3082b01329cbcd6f72a5ac2000669625
```

## Ledger Storage

R89 appends matched review records to:

```text
logs/hammer_radar_forward/human_confirmation_records.ndjson
```

Persisted records store phrase hashes rather than raw supplied phrases. Status and dry-run responses may still expose required phrases because R85, R86, and R88 already expose those operator texts for manual review.

Record types:

- `R85_TINY_LIVE_TICKET_REVIEW_APPROVAL`
- `R86_MANUAL_FUNDING_AND_ENV_CHECKLIST`
- `R88_FINAL_HUMAN_REVIEW_APPROVAL`

## Dry-Run And Write Behavior

Default behavior is:

```text
dry_run=true
write=false
```

No record is written unless both are true:

```text
dry_run=false
write=true
```

Wrong or missing phrases do not write confirmation records. Partial exact phrases can write the matched record types and produce `REVIEW_RECORDS_PARTIAL`. All exact phrases can produce `REVIEW_RECORDS_RECORDED_FOR_REVIEW`, but that is still review evidence only.

## Review-Only Guarantee

Every R89 payload and persisted record keeps:

```text
review_only=true
executable=false
env_modified=false
order_type=not_created
order_payload_created=false
execution_attempted=false
network_allowed=false
secrets_shown=false
```

Persisted review records are not execution permission. R87 remains intact:

```text
LIVE_ENV_ARMING_NOT_ALLOWED_YET
EXECUTION_BOUNDARY_INTACT
```

## API

```text
POST /live-arming/human-confirmations/record
GET /live-arming/human-confirmations/status
GET /live-arming/human-confirmations
```

The POST route defaults to dry-run/no-write and never creates order material.

## CLI

Dry-run status:

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward human-confirmations
```

Write exact review records only when explicitly supplied:

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward human-confirmations --write \
  --r85-approval-phrase "APPROVE_TINY_LIVE_REVIEW normal|BTCUSDT|13m|long|ladder_close_50_618 764df0c3cea3357416872be8d47e0f6189324cc8fbd0711dc5d1c8385ba114d8" \
  --r86-manual-funding-phrase "CONFIRM_MANUAL_FUNDING BTCUSDT MAX_MARGIN_44 MAX_LOSS_4.44 NO_BALANCE_CHECK" \
  --r86-live-env-review-phrase "CONFIRM_LIVE_ENV_REVIEW_ONLY KILL_SWITCH_ON LIVE_EXEC_DISABLED NO_ORDER" \
  --r86-max-loss-ack-phrase "ACK_MAX_LOSS_4.44_USDT" \
  --r86-exact-candidate-ack-phrase "ACK_TINY_LIVE_CANDIDATE normal|BTCUSDT|13m|long|ladder_close_50_618 764df0c3cea3357416872be8d47e0f6189324cc8fbd0711dc5d1c8385ba114d8" \
  --r88-final-approval-phrase "FINAL_REVIEW_ACK normal|BTCUSDT|13m|long|ladder_close_50_618 764df0c3cea3357416872be8d47e0f6189324cc8fbd0711dc5d1c8385ba114d8 b82fac02035b4a1b784548823c42f15c3082b01329cbcd6f72a5ac2000669625"
```

## Smoke Commands

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward human-confirmations | sed -n '1,320p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward final-review-packet | sed -n '1,240p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward live-env-boundary-review | sed -n '1,200p'
```

## Next Phase Recommendation

R90 should add Review Record Aggregator + Arming Readiness Snapshot. It should remain non-executable unless a later phase explicitly authorizes a separate live execution path with human approval, live-env changes, and safety validation.
