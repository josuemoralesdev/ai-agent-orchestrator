# R125 Autonomous Paper Lane Execution

Phase: R125

Status: IMPLEMENTED

Classification:
- Primary: NEW CAPABILITY
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DIAGNOSTIC / AUDIT
- Duplicate risk level: HIGH

## What R125 Adds

R125 adds autonomous paper lane execution records for fresh candidates routed by the R123 fresh signal router through the R122/R124 lane-control architecture.

The implementation lives in:

```text
src/app/hammer_radar/operator/autonomous_paper_lane_execution.py
```

It writes append-only paper records to:

```text
logs/hammer_radar_forward/autonomous_paper_lane_executions.ndjson
```

## Why This Is The Next Bridge

Manual approval is too slow for 4m, 8m, and 13m lanes. R122 moved operator intent from individual stale signals into configured lanes. R123 routes fresh candidates into those lanes. R124 lets the operator change lane modes safely.

R125 is the next bridge: it lets fresh routed candidates create auditable paper records automatically, while preserving the hard boundary that no real order can be placed.

## Candidate To Paper Record Flow

A routed candidate can become a paper lane record only when:

- `route_status` is `ROUTED_TO_LANE`
- the lane exists
- the lane mode is eligible for R125 paper handling
- the candidate is still inside the lane `freshness_seconds`
- `max_daily_trades` is not exceeded
- `cooldown_after_loss_minutes` is not active after a losing paper record
- source safety fields report no execution, no order payload, no network, and no secrets
- paper/live separation remains intact

Preview mode is the default and writes nothing.

## Lane Mode Behavior

- `disabled`: blocked.
- `paper`: creates `PAPER_ENTRY_RECORDED` when eligible.
- `armed_dry_run`: creates `ARMED_DRY_RUN_ENTRY_RECORDED` when eligible.
- `tiny_live`: R125 still does not create a real order. It may create `PAPER_SHADOW_FOR_TINY_LIVE` only when R123/R122 safety allows the route.

Tiny-live lane mode remains below R106/global live gates and is not execution authority.

## Freshness, Limits, And Cooldowns

Freshness uses the lane `freshness_seconds` window enforced by R123 routing.

Daily limits use the R125 paper lane ledger and count non-blocked records for the same `lane_key` on the current UTC day.

Cooldowns use the same ledger. A same-lane record with a loss marker such as negative `pnl_pct` activates `cooldown_after_loss_minutes` until the cooldown window expires.

## No Binance Calls

R125 does not:

- place orders
- create Binance order payloads
- call Binance order endpoints
- send signed requests
- call account or balance endpoints
- mutate env files
- enable global live execution
- bypass R106/global gates
- create live endpoints

The safety fields remain:

```json
{"order_placed":false,"real_order_placed":false,"execution_attempted":false,"order_payload_created":false,"network_allowed":false,"secrets_shown":false,"paper_live_separation_intact":true}
```

## CLI

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  autonomous-paper-lane-execution
```

Rejected write example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  autonomous-paper-lane-execution \
  --execute-paper \
  --confirm-paper-only "wrong"
```

Confirmed paper-only writes require the exact phrase:

```text
I CONFIRM PAPER LANE EXECUTION ONLY; NO REAL ORDER; NO BINANCE CALL.
```

R125 supports:

- `--execute-paper`
- `--lane-key <lane_key>`
- `--all-lanes`
- `--confirm-paper-only "<exact phrase>"`

## Audit Ledger

Confirmed eligible records are appended to:

```text
logs/hammer_radar_forward/autonomous_paper_lane_executions.ndjson
```

Rejected and preview-only commands do not write the ledger.

## Next Phases

- R126 first tiny-live lane execution: design the first tiny-live lane execution path only after R125 paper lane execution works, a fresh routed candidate exists, R106/global gates are ready, the lane is explicitly configured, and the operator gives explicit live confirmation.
- R127 live lane kill-switch rehearsal: rehearse the lane-level live kill switch before any broader live expansion.
- R128 post-paper performance promotion: use R125 paper results to decide whether any lane can be promoted.
