# R120 First-Live Targeted Clearing Pack

Phase: R120

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## What R120 Adds

R120 adds one diagnostic CLI command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-targeted-clearing-pack
```

The command consumes the R119 blocker-clearing workbench and chooses the next safest clearing lane for the operator. It emits the selected lane, the reason it is first, preview and evidence-only commands, the exact evidence-only confirmation phrase, stop conditions, and the post-clear recheck sequence.

Optional arguments:

```bash
--lane <lane_id>
--all-evidence-lanes
--authorization-check
```

## What R120 Does Not Add

R120 does not add:
- live trading
- order placement
- live env changes
- Binance order calls
- evidence-to-execution wiring
- authorization authority
- executable order payloads
- live order endpoints
- service restarts

It always reports:
- `live_ready=false`
- `execution_enabled_by_targeted_clearing=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `real_order_possible=false`
- `secrets_shown=false`

## Why R120 Chooses Targeted Clearing Now

Current source state from R119/R118 remains blocked:
- R119: `WORKBENCH_READY`
- R118: `FINAL_REVIEW_BLOCKED`
- R112: `EVIDENCE_PARTIAL`
- R106: `FIRST_LIVE_BLOCKED`
- paper/live separation intact
- live ready false

Because R118 is not `READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION`, R120 chooses targeted clearing mode. It must not prepare an authorization request while R118 is blocked.

## Lane Selection Priority

When no lane is specified, R120 chooses the first applicable lane in this order:

1. `evidence_records_lane` if evidence is partial or missing
2. `approval_records_lane`
3. `sacred_button_safety_lane`
4. `tiny_size_max_loss_lane`
5. `account_funding_read_only_lane`
6. `protective_orders_lane`
7. `live_adapter_boundary_lane`
8. `environment_flags_review_lane`
9. `candidate_freshness_lane`
10. `final_gate_recheck_lane`

Allowed lane ids:
- `evidence_records_lane`
- `approval_records_lane`
- `account_funding_read_only_lane`
- `protective_orders_lane`
- `live_adapter_boundary_lane`
- `tiny_size_max_loss_lane`
- `environment_flags_review_lane`
- `sacred_button_safety_lane`
- `emergency_and_position_review_lane`
- `candidate_freshness_lane`
- `final_gate_recheck_lane`

Invalid lane ids are rejected with `TARGETED_CLEARING_BLOCKED_UNSAFE` and no execution side effects.

## Command Examples

Default targeted clearing pack:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-targeted-clearing-pack
```

Sacred button lane:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-targeted-clearing-pack --lane sacred_button_safety_lane
```

Show all evidence lane commands:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-targeted-clearing-pack --all-evidence-lanes
```

Authorization readiness check:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-targeted-clearing-pack --authorization-check
```

If R118 remains blocked, authorization check returns `AUTHORIZATION_REQUEST_NOT_READY`.

## Confirmation Phrase

R120 uses the existing R116 evidence-only phrase:

```text
I CONFIRM EVIDENCE RECORDING ONLY; NO LIVE ORDER; NO ENV CHANGE.
```

This phrase authorizes evidence recording only. It is not live-order authorization.

## Post-Clear Recheck Sequence

After clearing evidence, run:

1. `first-live-evidence-status`
2. `first-live-prerequisite-recheck-after-evidence`
3. `first-live-post-evidence-gate-recheck`
4. `first-live-blocker-clearing-workbench`
5. `first-live-activation-final-review`
6. `first-live-activation-gate`
7. `curl -s http://127.0.0.1:8015/operator/approval-cockpit/state`

Stop if R118 remains blocked after evidence, if the active tuple changes, if R109 can place an order, if paper/live separation breaks, if any secret appears, if any order or execution field becomes true, if env flag changes are attempted, or if a Binance order endpoint appears.

## Authorization Boundary

R120 can report `READY_TO_PREPARE_AUTHORIZATION_REQUEST` only when R118 says `READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION`. That status only prepares a later explicit authorization request phase. It is not live execution authorization.

R106 remains the first-live activation authority. R109 remains intent-only.

## Ledger Location

R120 appends diagnostic records to:

```text
logs/hammer_radar_forward/first_live_targeted_clearing_packs.ndjson
```

Each record includes:
- `event_type=FIRST_LIVE_TARGETED_CLEARING_PACK`
- `targeted_clearing_id`
- `recorded_at_utc`
- status
- active tuple
- mode decision
- selected lane
- authorization status
- hard safety booleans
- source surfaces used

The ledger is diagnostic evidence only. It is not authorization and not execution authority.

## How This Prepares R121

R121 should recheck evidence after the operator uses the R120/R116 commands. If R118 remains blocked, R121 should produce the next targeted lane. If R118 becomes ready, R121 should prepare an explicit authorization request phase while still remaining non-executing unless a later phase is explicitly authorized.
