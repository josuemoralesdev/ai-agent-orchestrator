# R117 First-Live Post-Evidence Gate Recheck

Phase: R117

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## What R117 Adds

R117 adds one CLI post-evidence recheck report:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-post-evidence-gate-recheck
```

The report reads R112 evidence status, the latest R116 assisted-run ledger record when present, and fresh non-recording R113/R111/R110/R106/R109 status surfaces. It then reports whether evidence appears to reduce blockers and whether the system can move to a final R106 activation-gate review phase.

R117 writes an append-only report ledger at:

```text
logs/hammer_radar_forward/first_live_post_evidence_gate_rechecks.ndjson
```

## What R117 Does Not Add

R117 does not add:
- live trading
- live env changes
- Binance order calls
- Binance account, balance, funding, or position calls
- evidence-to-execution wiring
- approval-to-execution wiring
- executable order payloads
- live order endpoints
- execution authority
- service restarts

It always reports:
- `live_ready=false`
- `execution_enabled_by_post_evidence_recheck=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `real_order_possible=false`
- `secrets_shown=false`

## How R117 Uses R112/R113/R116

R117 uses R112 as the evidence source of truth through `first-live-evidence-status`.

R117 uses R113 as the evidence-backed prerequisite recheck surface. The R117 blocker map is derived from R113 group results and keeps the same required group set:
- `candidate_freshness`
- `approval_records`
- `binance_credentials_presence`
- `account_funding_read_only_check`
- `protective_orders_readiness`
- `live_adapter_boundary`
- `tiny_position_size_cap`
- `max_loss_cap`
- `environment_flag_review`
- `confirmation_phrase_preparation`
- `sacred_button_safety`
- `duplicate_source_conflicts`

R117 reads the latest R116 assisted-run ledger record if one exists. R116 is evidence-recording assistance only; its presence is context, not authority.

## Status Meanings

`POST_EVIDENCE_BLOCKED` means the evidence/gate chain cannot move forward. This is forced when R106 remains `FIRST_LIVE_BLOCKED`, evidence is missing, the active tuple is inconsistent or missing, R109 can place orders, paper/live separation is not intact, or any safety field indicates order placement, execution, real-order possibility, or secret exposure.

`POST_EVIDENCE_PARTIAL` means accepted evidence exists, but required evidence or gate blockers remain. This is still non-executing and still cannot be treated as live readiness.

`POST_EVIDENCE_READY_FOR_ACTIVATION_GATE_RECHECK` means evidence is ready for prerequisite recheck, R113 is ready for R106, R106 is currently activation-ready, R109 remains intent-only with `can_place_order=false`, paper/live separation is intact, and all R117 safety fields remain false. It still does not return `live_ready=true`.

## Evidence-To-Gate Delta

The `gate_delta` section reports:
- current R106 status
- current R113 status
- remaining blocker count
- missing evidence count
- cleared group count
- still-blocked group count
- evidence-needed group count
- whether evidence appears to reduce blockers
- whether the activation gate is currently ready

This is a comparison aid only. R117 does not replace R106 and does not create a second gate authority.

## Activation Readiness Summary

The `activation_readiness_summary` reports whether the operator can consider the next non-executing activation review phase. It includes:
- `can_consider_activation_phase`
- reason
- required items before activation review
- current R106 status
- R109 sacred-button `can_place_order`
- R109 intent-only status
- paper/live separation status

## Final Recheck Command Pack

R117 emits exact commands for:
- evidence status
- R113 prerequisite recheck
- R111 prerequisite clearing
- R110 burn-down
- R106 activation gate
- R109 cockpit state

The cockpit command remains a local operator API read:

```bash
curl -s http://127.0.0.1:8015/operator/approval-cockpit/state
```

## Safety Constraints

R117 preserves:
- R106 as first-live activation authority
- R109 sacred button as intent-only
- no order placement
- no execution attempt
- no live execution enablement
- no evidence-to-execution wiring
- no secret values shown
- paper/live separation

## Why This Is Non-Executing

R117 calls only existing inspection/status builders and reads ledgers. It records only an R117 diagnostic ledger entry. It does not call execution connectors, does not produce signed payloads, does not edit `.env` or live flags, and does not expose a new API endpoint.

Evidence can support a later review, but evidence does not equal execution authorization.

## How This Prepares R118

R117 produces the single post-evidence package R118 needs for final activation-gate review. R118 should inspect the R117 report, R106 gate state, R109 sacred-button state, and remaining blockers to decide whether the operator can request explicit first-live execution authorization in a later phase.

R118 must remain non-executing unless a future phase explicitly authorizes live execution.
