# R113 First-Live Prerequisite Recheck After Evidence

Phase: R113

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## What R113 Adds

R113 adds a CLI-only prerequisite recheck after R112 operator evidence recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-prerequisite-recheck-after-evidence
```

The command composes:
- R106 first-live activation gate
- R109 sacred cockpit state
- R110 burn-down
- R111 prerequisite clearing
- R112 evidence status

It reports whether accepted R112 evidence reduces R111 prerequisite blockers and whether the operator is closer to an R106 `FIRST_LIVE_ACTIVATION_READY` recheck.

## What R113 Does Not Add

R113 does not add:
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
- `execution_enabled_by_recheck=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `real_order_possible=false`
- `secrets_shown=false`

## How R113 Uses R112 Evidence

R113 reads the append-only R112 ledger:

```text
logs/hammer_radar_forward/first_live_operator_evidence.ndjson
```

Only accepted records count. R113 groups accepted evidence by the same `candidate_id`, `risk_contract_hash`, and `packet_hash` tuple. Complete or partial evidence can reduce evidence-backed prerequisite groups, but it cannot create live readiness.

## Recheck Statuses

- `RECHECK_BLOCKED`: no meaningful prerequisite reduction is available, or blockers remain dominant.
- `RECHECK_PARTIAL`: at least one group is clear, but blockers, missing evidence, or unknowns remain.
- `RECHECK_READY_FOR_R106`: all R113 prerequisite groups are clear and the next action is to re-run R106.

`RECHECK_READY_FOR_R106` is still not execution authority. It only points the operator back to the R106 gate.

## Evidence-To-Blocker Mapping

R113 maps evidence to these prerequisite groups:

| Group | Evidence types |
|---|---|
| `approval_records` | `APPROVAL_INTENT_REVIEWED`, `HUMAN_REVIEW_R85`, `HUMAN_REVIEW_R86`, `HUMAN_REVIEW_R88` |
| `account_funding_read_only_check` | `ACCOUNT_FUNDING_READ_ONLY_CHECK`, `NO_CONFLICTING_POSITION_REVIEWED` |
| `protective_orders_readiness` | `PROTECTIVE_ORDERS_REVIEWED` |
| `live_adapter_boundary` | `LIVE_ADAPTER_BOUNDARY_REVIEWED` |
| `tiny_position_size_cap` | `TINY_SIZE_MAX_LOSS_DEFINED` |
| `max_loss_cap` | `TINY_SIZE_MAX_LOSS_DEFINED` |
| `environment_flag_review` | `ENVIRONMENT_FLAGS_REVIEWED` |
| `sacred_button_safety` | `SACRED_BUTTON_INTENT_ONLY_VERIFIED` plus R109 `can_place_order=false` and `records_intent_only=true` |

Some groups still require non-evidence runtime state or future operator action:
- `candidate_freshness`
- `binance_credentials_presence`
- `confirmation_phrase_preparation`
- `duplicate_source_conflicts`

## Activation Distance

The `activation_distance` object reports:
- current R106 status
- remaining blocker count after evidence recheck
- missing evidence count
- highest-priority next blocker
- next phase or command needed

This is a diagnostic distance indicator only. R106 remains the activation authority.

## Commands

Run R113:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-prerequisite-recheck-after-evidence
```

Run without writing the R113 ledger:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-prerequisite-recheck-after-evidence --no-record
```

Related commands:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-activation-gate
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-prerequisite-clearing
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-evidence-status
curl -s http://127.0.0.1:8015/operator/approval-cockpit/state
```

## Ledger Location

R113 writes append-only NDJSON to:

```text
logs/hammer_radar_forward/first_live_prerequisite_rechecks.ndjson
```

Each record includes:
- `event_type=FIRST_LIVE_PREREQUISITE_RECHECK_AFTER_EVIDENCE`
- `recheck_id`
- `recorded_at_utc`
- source statuses
- evidence status
- blocker recheck rows
- activation distance
- safety booleans
- source surfaces used

## Safety Constraints

R113 preserves:
- no orders
- no live trading enablement
- no Binance order calls
- no Binance account or balance calls
- no env edits
- no exposed secrets
- no execution authority
- no evidence-to-execution wiring
- no live order endpoint
- paper/live separation

The sacred button remains safe:
- `sacred_button_can_place_order=false`
- cockpit records intent only
- R109 remains intent-only
- R106 remains authority

## Why This Is Still Non-Executing

R113 only reads existing readiness/evidence surfaces and writes a diagnostic recheck ledger. It does not submit orders, create signed payloads, configure live adapters, call Binance, edit live flags, or authorize execution.

Even complete R112 evidence can only reduce evidence-backed prerequisite groups. The operator must still re-run R106, and any future live order remains blocked until a later explicitly authorized phase.

## How This Prepares R114

R113 identifies the exact groups that still need evidence or runtime clearing. R114 should turn those gaps into exact guided clearing commands:
- generate record-first-live-evidence commands for the active tuple
- generate the recheck sequence
- preserve no order placement
- preserve no live flag modification unless a later phase explicitly authorizes it
