# R104 Tiny-Live Armed Dry Run

Phase: R104

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

Purpose: exercise the tiny-live arming chain as a dry run while proving that no real order can be placed.

## 1. What R104 Adds

R104 adds a read-only, audit-recording inspect command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-armed-dry-run
```

The command composes:
- R102 final live preflight
- R103 final approval intent records
- risk contract hash
- final review packet hash
- live execution flags
- global kill switch state
- connector mode
- protective readiness
- stale candidate protection
- paper/live separation

It records an append-only dry-run row and returns `READY_FOR_DRY_RUN` or `BLOCKED_FOR_DRY_RUN`.

## 2. What R104 Does Not Add

R104 does not add:
- live trading
- live env changes
- live arming
- order placement
- Binance order calls
- signed order payload creation
- Telegram approval-to-execution wiring
- a new readiness source of truth
- an API endpoint

## 3. Exact Command To Run

Default candidate:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-armed-dry-run
```

Explicit candidate:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-armed-dry-run \
  --candidate-id 'normal|BTCUSDT|13m|long|ladder_close_50_618'
```

No-record preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-armed-dry-run --no-record
```

## 4. Example BLOCKED_FOR_DRY_RUN Output

Shape:

```json
{
  "status": "BLOCKED_FOR_DRY_RUN",
  "live_ready": false,
  "dry_run_only": true,
  "order_placed": false,
  "execution_attempted": false,
  "real_order_possible": false,
  "blockers": [
    "final preflight is BLOCKED",
    "missing final approval intent",
    "stale candidate risk",
    "environment boundary blocked",
    "protective readiness false",
    "live order adapter not configured"
  ],
  "final_preflight_status": "BLOCKED",
  "approval_intent_present": false,
  "approval_intent_status": "MISSING",
  "connector_mode": "DRY_RUN_ONLY",
  "live_execution_enabled": false,
  "live_orders_allowed": false,
  "global_kill_switch": true
}
```

The actual output includes hashes when available, sanitized Binance credential presence booleans, full blocker lists, source surfaces, and the ledger path.

## 5. Why READY_FOR_DRY_RUN Is Not LIVE_READY

`READY_FOR_DRY_RUN` only means the dry-run prerequisites are present and internally consistent. It never means the system is live-ready.

The R104 adapter always returns:
- `live_ready=false`
- `dry_run_only=true`
- `order_placed=false`
- `execution_attempted=false`
- `real_order_possible=false`

Any future live execution requires a separate explicitly authorized phase.

## 6. Safety Constraints

R104 preserves:
- no live orders
- no Binance order endpoint calls
- no account or balance calls
- no env flag edits
- no secret exposure
- no global kill switch override
- no Telegram approval intent treated as execution approval
- no weakening of paper/live separation
- no executable payload creation

R104 returns `BLOCKED_FOR_DRY_RUN` if final preflight is blocked, approval intent is missing or invalid, hashes are missing or mismatched, stale candidate risk exists, environment boundary is blocked, protective readiness is false, or the live order adapter is not configured.

## 7. Ledger Location

Dry-run records are appended under the Hammer Radar log directory:

```text
tiny_live_armed_dry_runs.ndjson
```

Each record includes status, hashes, approval-intent status, blockers, live flags, connector mode, safety booleans, and source surfaces.

## 8. How This Prepares R105 One Tiny Live Order Protocol

R105 can use the R104 dry-run ledger to verify that:
- final preflight was called
- final approval intent was considered
- hashes were checked
- live flags were inspected
- stale candidate and environment boundaries remained visible
- order placement remained impossible during dry run

R105 must still be a separate future phase with explicit authorization before any live order protocol is defined or executed.
