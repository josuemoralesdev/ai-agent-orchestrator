# R114 First-Live Evidence-Guided Clearing Actions

Phase: R114

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## What R114 Adds

R114 adds a CLI-only action-pack generator for the active first-live candidate/hash tuple:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-evidence-guided-actions
```

The command returns JSON with:
- active `candidate_id`, `risk_contract_hash`, and `packet_hash`
- missing R112 evidence types still needed for R113/R111 clearing
- exact `record-first-live-evidence` commands for each missing evidence type
- grouped actions for approval records, account/funding, protective orders, adapter boundary, risk limits, environment, sacred button, emergency, and position conflicts
- exact recheck commands for R112, R113, R111, R110, R106, and R109 cockpit state
- safety booleans proving the command is non-executing

R114 writes append-only NDJSON to:

```text
logs/hammer_radar_forward/first_live_evidence_guided_actions.ndjson
```

## What R114 Does Not Add

R114 does not add:
- live trading
- live env changes
- Binance order calls
- Binance account, funding, position, or balance calls
- evidence-to-execution wiring
- approval-to-execution wiring
- a live order endpoint
- execution authority
- service restarts

It always reports:
- `live_ready=false`
- `execution_enabled_by_guided_actions=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `real_order_possible=false`
- `secrets_shown=false`

## How R114 Uses R112 And R113

R114 reuses R112 as the only evidence-recording surface. It does not create a second evidence ledger or a second evidence validator.

R114 reuses R113 to identify evidence-backed prerequisite gaps after current R112 records. It also composes R111, R110, R106, and R109 state so the operator can see the current source statuses before recording anything.

The active tuple is resolved from the current first-live surfaces. If R114 cannot find a complete tuple, or the tuple sources conflict, it returns:

```text
ACTIONS_BLOCKED_NO_ACTIVE_TUPLE
```

No evidence commands are emitted in that blocked state.

## Command Generator Behavior

When the active tuple is present, R114 emits one command per missing supported evidence type:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward record-first-live-evidence \
  --evidence-type APPROVAL_INTENT_REVIEWED \
  --candidate-id '<candidate_id>' \
  --risk-contract-hash '<risk_contract_hash>' \
  --packet-hash '<packet_hash>' \
  --note 'Reviewed approval intent record for this tuple; no key values recorded.'
```

The generated commands are meant to be edited by the operator only after personal verification. They are evidence records, not trade instructions.

## Evidence Command Examples

Read-only funding evidence:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward record-first-live-evidence \
  --evidence-type ACCOUNT_FUNDING_READ_ONLY_CHECK \
  --candidate-id '<candidate_id>' \
  --risk-contract-hash '<risk_contract_hash>' \
  --packet-hash '<packet_hash>' \
  --note 'Reviewed funding readiness via read-only operator procedure; no order call made.'
```

Sacred button evidence:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward record-first-live-evidence \
  --evidence-type SACRED_BUTTON_INTENT_ONLY_VERIFIED \
  --candidate-id '<candidate_id>' \
  --risk-contract-hash '<risk_contract_hash>' \
  --packet-hash '<packet_hash>' \
  --note 'Verified sacred button state is intent-only with can_place_order false.'
```

Protective-order readiness evidence:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward record-first-live-evidence \
  --evidence-type PROTECTIVE_ORDERS_REVIEWED \
  --candidate-id '<candidate_id>' \
  --risk-contract-hash '<risk_contract_hash>' \
  --packet-hash '<packet_hash>' \
  --note 'Reviewed protective stop and take-profit readiness for this tuple; no order created.'
```

## Active Tuple Safety

Every generated evidence command includes the same active:
- `candidate_id`
- `risk_contract_hash`
- `packet_hash`

If these are missing or inconsistent across current source surfaces, R114 blocks command generation. The operator must resolve the tuple before recording evidence.

## Secret-Handling Warning

Do not paste secret values, keys, tokens, private credential material, account identifiers, signatures, auth headers, or `.env` values into `--note`.

R112 rejects notes with obvious secret-risk terms and redacts them, but the operator should still write notes using safe summaries only.

## Recheck Sequence

After recording only personally verified evidence, run:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-evidence-status
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-prerequisite-recheck-after-evidence
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-prerequisite-clearing
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-burn-down
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-activation-gate
curl -s http://127.0.0.1:8015/operator/approval-cockpit/state
```

Stop if any blocker remains.

## Ledger Location

R114 writes:

```text
logs/hammer_radar_forward/first_live_evidence_guided_actions.ndjson
```

Each record includes:
- `event_type=FIRST_LIVE_EVIDENCE_GUIDED_ACTIONS`
- `action_pack_id`
- `recorded_at_utc`
- status
- active tuple
- missing evidence types
- evidence command count
- grouped actions
- safety booleans
- source surfaces used

## Why This Is Still Non-Executing

R114 only prints commands that call R112 evidence recording and then recheck existing diagnostic surfaces. It does not call Binance, create signed payloads, edit env flags, wire evidence to execution, or authorize any order.

R106 remains the activation authority. R109 remains intent-only. Even a complete R114 action pack only prepares evidence for later rechecks.

## How This Prepares R115

R115 should turn the R114 action pack into an operator runbook for actually recording the evidence and rerunning R112/R113/R111/R106. R115 must remain non-executing unless a later phase explicitly authorizes a different scope.
