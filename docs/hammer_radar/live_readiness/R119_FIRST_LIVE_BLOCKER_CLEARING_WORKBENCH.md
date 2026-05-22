# R119 First-Live Blocker Clearing Workbench

Phase: R119

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## What R119 Adds

R119 adds one diagnostic CLI workbench:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-blocker-clearing-workbench
```

The workbench reads R118 final-review state and turns the remaining first-live blockers into exact clearing lanes for today's tiny-live readiness push. It organizes what can be cleared by evidence recording, what needs read-only operator verification, what needs config review, what needs market freshness, and what must stay blocked until later explicit authorization.

R119 writes append-only NDJSON to:

```text
logs/hammer_radar_forward/first_live_blocker_clearing_workbench.ndjson
```

## What R119 Does Not Add

R119 does not add:
- live trading
- order placement
- live env changes
- Binance order calls
- Binance account, balance, funding, or position calls
- evidence-to-execution wiring
- authorization authority
- executable order payloads
- live order endpoints
- service restarts

It always reports:
- `live_ready=false`
- `execution_enabled_by_workbench=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `real_order_possible=false`
- `secrets_shown=false`

## Clearing Lanes

R119 emits these lanes:
- `evidence_records_lane`
- `candidate_freshness_lane`
- `approval_records_lane`
- `binance_credentials_lane`
- `account_funding_read_only_lane`
- `protective_orders_lane`
- `live_adapter_boundary_lane`
- `tiny_size_max_loss_lane`
- `environment_flags_review_lane`
- `sacred_button_safety_lane`
- `final_gate_recheck_lane`
- `future_authorization_lane`

Each lane includes owner, current status, target status, commands, evidence commands, verification commands, stop conditions, and safety notes. The future authorization lane is intentionally `can_clear_now=false`.

## Immediate Operator Sequence

1. Confirm current active tuple and freshness.
2. Run R116 preview for all groups.
3. Record only personally verified evidence using R116 execute-evidence with exact confirmation.
4. Run R112 evidence status.
5. Run R113 prerequisite recheck.
6. Run R117 post-evidence gate recheck.
7. Run R118 final review.
8. If R118 remains blocked, follow remaining clearing lanes.
9. Do not request authorization until R118 says ready.
10. Never place order from R119.

## Assisted Evidence Commands

Preview all groups:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-evidence-assisted-run --all-groups
```

Preview a single group:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-evidence-assisted-run --group <group>
```

Rejected execute example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-evidence-assisted-run --group sacred_button_review --execute-evidence --confirm-evidence-only "WRONG CONFIRMATION"
```

Valid execute template, `OPERATOR_REVIEW_REQUIRED`:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-evidence-assisted-run --group <group> --execute-evidence --confirm-evidence-only "I CONFIRM EVIDENCE RECORDING ONLY; NO LIVE ORDER; NO ENV CHANGE."
```

This exact phrase authorizes evidence recording only. It is not live-order authorization.

## Stop Conditions

Stop immediately if any of these appear:
- active tuple changed
- candidate stale
- R106 remains blocked after evidence
- sacred button can_place_order true
- sacred button records_intent_only false
- paper_live_separation_intact false
- secrets shown
- order placed true
- execution attempted true
- real_order_possible true from any non-execution phase
- env flag change attempted
- Binance order endpoint appears
- evidence note includes secrets
- R118 does not say ready

## Authorization Boundary

R119 cannot request authorization, cannot authorize execution, and cannot place orders. It only organizes clearing work. It prepares a future R120 or R119.5 only if R118 becomes ready.

R106 remains the first-live activation gate authority. R109 remains intent-only.

## Ledger Location

R119 appends workbench records to:

```text
logs/hammer_radar_forward/first_live_blocker_clearing_workbench.ndjson
```

Each record includes:
- `event_type=FIRST_LIVE_BLOCKER_CLEARING_WORKBENCH`
- `workbench_id`
- `recorded_at_utc`
- status
- active tuple
- source statuses
- clearing lanes
- immediate operator sequence
- hard safety booleans
- source surfaces used

The ledger is diagnostic evidence only. It is not authorization and not execution authority.

## How This Prepares R120

If blockers remain, R120 should target the highest remaining clearing lane.

If R118 becomes ready after evidence, R120 may become an explicit authorization request phase, still non-executing by default.
