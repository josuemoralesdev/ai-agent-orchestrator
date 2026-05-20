# R102 One-Command Final Live Preflight

Phase: R102

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, DUPLICATE RISK
- Duplicate risk level: HIGH

## 1. What R102 Adds

R102 adds one operator-facing final preflight command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward final-live-preflight
```

The command returns a single structured JSON result with:
- `status`: `READY` or `BLOCKED`
- exact `blockers`
- `warnings`
- live execution flag state
- live order flag state
- global kill switch state
- Binance credential presence booleans only
- risk contract hash
- final review packet hash
- human approval record state
- protective order readiness
- stale-candidate protection state
- Telegram configuration state
- paper/live separation status
- `source_surfaces_used`

## 2. What R102 Does Not Add

R102 does not add:
- live trading
- live env changes
- order placement
- signed payload creation
- Binance order or account calls
- Telegram approval execution wiring
- service restarts
- a second readiness source of truth

R102 is read-only composition over existing readiness, preflight, boundary, and status surfaces.

## 3. Why This Is Not A New Source Of Truth

The final preflight adapter does not make independent trading decisions. It gathers and normalizes outputs from existing modules:
- `readiness.build_readiness_payload`
- `live_arming_preflight.build_live_arming_preflight`
- `live_env_boundary_review.build_live_env_boundary_review`
- `strategy_performance.build_live_eligibility_matrix`
- `strategy_promotion_watcher.build_strategy_promotion_status`
- `tiny_live_risk_contract.build_tiny_live_risk_contract_payload`
- `final_human_review_packet.build_final_human_review_packet`
- `human_confirmation_records.build_human_confirmation_records_status`
- `review_record_aggregator.build_review_record_arming_snapshot`
- `live_preflight.build_promoted_strategy_preflight`
- `binance_live_status.build_binance_live_status`
- `binance_futures_connector.build_connector_status`
- `binance_futures_connector.build_protective_status`
- `notification_watcher.notification_status`

The adapter reports blockers from those surfaces and adds only top-level gate labels required for operator readability.

## 4. Exact Command To Run

Default candidate:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward final-live-preflight
```

Explicit candidate:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward final-live-preflight \
  --candidate-id 'normal|BTCUSDT|13m|long|ladder_close_50_618'
```

## 5. Example BLOCKED Output

Shape:

```json
{
  "status": "BLOCKED",
  "blockers": [
    "live execution disabled",
    "live orders disabled",
    "global kill switch active",
    "missing Binance credentials",
    "dry-run-only connector mode: DRY_RUN_ONLY",
    "missing final review packet",
    "missing human approval record",
    "protective readiness false",
    "live order adapter not configured",
    "stale candidate risk",
    "environment boundary blocked"
  ],
  "live_execution_enabled": false,
  "live_orders_allowed": false,
  "global_kill_switch": true,
  "connector_mode": "DRY_RUN_ONLY",
  "binance_credentials_present": {
    "api_key_present": false,
    "api_secret_present": false
  },
  "paper_live_separation_intact": true
}
```

The actual command includes more fields, including hashes, warnings, source statuses, and `source_surfaces_used`.

## 6. How This Prepares R103

R103 can use the R102 output as a read-only operator checklist before recording final Telegram approval phrases. R103 should not execute orders. It should guide the operator through missing R85/R86/R88 review records and preserve the existing R87/R90 boundaries until a later explicitly authorized phase.

## 7. Safety Constraints

R102 must preserve:
- no live orders
- no Binance live/trading calls
- no account/balance calls
- no executable payloads
- no env edits
- no secret exposure
- no Telegram approval-to-execution wiring
- no bypass of human review records
- no weakening of paper/live separation
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `secrets_shown=false`

If any critical gate is blocked, the final preflight status must be `BLOCKED`.
