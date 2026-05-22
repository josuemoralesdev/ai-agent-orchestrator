# R112 First-Live Operator Evidence Recording

Phase: R112

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## What R112 Adds

R112 adds CLI-only evidence recording for the first-live prerequisites identified by R111.

It records append-only NDJSON rows at:

```text
logs/hammer_radar_forward/first_live_operator_evidence.ndjson
```

The record command is:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward record-first-live-evidence \
  --evidence-type APPROVAL_INTENT_REVIEWED \
  --candidate-id 'normal|BTCUSDT|13m|long|ladder_close_50_618' \
  --risk-contract-hash '<risk_contract_hash>' \
  --packet-hash '<packet_hash>' \
  --note 'operator reviewed approval intent evidence'
```

The status command is:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-evidence-status
```

## What R112 Does Not Add

R112 does not add:
- live trading
- live env changes
- Binance order calls
- Binance account, funding, position, or balance calls
- approval-to-execution wiring
- Telegram-to-execution wiring
- a live order endpoint
- execution authority
- service restarts

Every record and status payload reports:
- `live_ready=false`
- `execution_enabled_by_evidence=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `real_order_possible=false`
- `secrets_shown=false`

## Evidence Types

Supported evidence types are:
- `APPROVAL_INTENT_REVIEWED`
- `HUMAN_REVIEW_R85`
- `HUMAN_REVIEW_R86`
- `HUMAN_REVIEW_R88`
- `ACCOUNT_FUNDING_READ_ONLY_CHECK`
- `PROTECTIVE_ORDERS_REVIEWED`
- `LIVE_ADAPTER_BOUNDARY_REVIEWED`
- `TINY_SIZE_MAX_LOSS_DEFINED`
- `ENVIRONMENT_FLAGS_REVIEWED`
- `SACRED_BUTTON_INTENT_ONLY_VERIFIED`
- `EMERGENCY_CANCEL_PATH_REVIEWED`
- `NO_CONFLICTING_POSITION_REVIEWED`

## Record Command Examples

Human review evidence:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward record-first-live-evidence \
  --evidence-type HUMAN_REVIEW_R85 \
  --candidate-id 'normal|BTCUSDT|13m|long|ladder_close_50_618' \
  --risk-contract-hash '<risk_contract_hash>' \
  --packet-hash '<packet_hash>' \
  --note 'R85 ticket review completed for this tuple'
```

Read-only account/funding evidence:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward record-first-live-evidence \
  --evidence-type ACCOUNT_FUNDING_READ_ONLY_CHECK \
  --candidate-id 'normal|BTCUSDT|13m|long|ladder_close_50_618' \
  --risk-contract-hash '<risk_contract_hash>' \
  --packet-hash '<packet_hash>' \
  --note 'read-only funding review completed; no order endpoint used'
```

Sacred button evidence:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward record-first-live-evidence \
  --evidence-type SACRED_BUTTON_INTENT_ONLY_VERIFIED \
  --candidate-id 'normal|BTCUSDT|13m|long|ladder_close_50_618' \
  --risk-contract-hash '<risk_contract_hash>' \
  --packet-hash '<packet_hash>' \
  --note 'R109 verified can_place_order=false and records_intent_only=true'
```

## Evidence Status

`first-live-evidence-status` returns:
- `EVIDENCE_MISSING` when the ledger has no rows
- `EVIDENCE_PARTIAL` when evidence is incomplete, rejected, or split across mismatched tuples
- `EVIDENCE_READY_FOR_PREREQ_RECHECK` only when all required evidence types are accepted for one consistent `candidate_id`, `risk_contract_hash`, and `packet_hash`

This status is only a signal that R113 can re-run prerequisite clearing. It is not live readiness and not execution permission.

## Secret Handling

R112 rejects notes that appear to contain secret material, including:
- `api key`
- `api_secret`
- `secret`
- `private key`
- `token`
- `password`

Secret-risk notes are not echoed back. The stored note is replaced with:

```text
[REDACTED_SECRET_RISK]
```

## Why Evidence Is Not Execution Authority

R112 writes audit evidence only. It does not call R106, change R106 output, change R109 button behavior, or create any execution path.

R106 remains the first-live activation authority. R109 remains intent-only. R112 records evidence that can be inspected later, but it cannot place an order or make a real order possible.

## How To Use This With R111

1. Run R111:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-prerequisite-clearing
```

2. Record safe R112 evidence for the groups R111 reports as `NEEDS_OPERATOR_EVIDENCE`.
3. Run R112 status:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-evidence-status
```

4. If status is `EVIDENCE_READY_FOR_PREREQ_RECHECK`, proceed to R113 prerequisite recheck.

## How This Prepares R113

R113 should consume the R112 evidence ledger alongside R111 prerequisite clearing and determine whether R106 blockers reduce for the same candidate/hash tuple.

R113 must remain non-executing unless a later phase explicitly authorizes execution.
