# R127 Lane Autonomy Control Loop Scaffold

Phase: R127

Status: IMPLEMENTED

Classification:
- Primary: NEW CAPABILITY
- Secondary: WIRING / INTEGRATION, DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## What R127 Adds

R127 adds the non-executing autonomous lane control loop scaffold:

```text
src/app/hammer_radar/operator/lane_autonomy_control_loop.py
```

The loop composes existing R122 lane controls, R123 fresh signal routing, and R125 paper lane ledger limits into autonomous decisions. It writes append-only decision records only when explicitly confirmed.

The ledger path is:

```text
logs/hammer_radar_forward/lane_autonomy_decisions.ndjson
```

## Why This Is The Real Autonomous Model

The operator should not approve each individual fast signal after it appears. The operator arms or disarms lanes, sets lane mode, and authorizes strategy/timeframe scope. The system then watches fresh routed candidates and decides whether the lane should ignore, observe, form paper entry intent, form dry-run intent, request tiny-live gate review, or block.

This moves Hammer Radar toward the intended operating model:

- operator controls global kill switch, lane mode, and strategy/timeframe authorization
- system controls fresh signal detection, lane matching, entry eligibility, risk intent, exit policy intent, cooldowns, daily limits, and decision ledgering

## Operator Switches Vs System Decisions

Operator-controlled surfaces:

- global kill switch and global live gates
- per-lane mode in `configs/hammer_radar/lane_controls.json`
- strategy/timeframe authorization represented by lane config and existing eligibility/gate surfaces

System-controlled decisions:

- fresh candidate routing through R123
- lane match and freshness checks
- max daily trades and cooldown checks using R125 paper ledgers
- max daily loss checks from existing paper results
- autonomy decision classification
- non-executing strategy intent preview
- append-only decision ledgering after exact confirmation

## Lane Mode Behavior

R127 decisions are:

- `IGNORE`: no useful fresh lane candidate, missing source, no matching lane, or no action required
- `PAPER_OBSERVE`: non-entry paper observation intent when applicable
- `PAPER_ENTRY_INTENT`: fresh routed `paper` lane candidate with limits clear
- `ARMED_DRY_RUN_INTENT`: fresh routed `armed_dry_run` lane candidate with limits clear
- `TINY_LIVE_GATE_REVIEW`: fresh routed `tiny_live` lane candidate with limits clear, still review-only
- `BLOCKED`: stale, lane-blocked, limit-blocked, cooldown-blocked, unsafe source, or executable-payload risk

`tiny_live` remains behind R106/global gates. R127 does not make tiny-live easier and does not authorize execution.

## Non-Executing Strategy Intent

Each decision includes a strategy intent with:

- `entry_reference`
- `stop_reference`
- `take_profit_reference`
- `score`
- `size_policy.type=risk_contract_reference`
- `size_policy.direct_live_quantity=null`
- `exit_policy.direct_exchange_payload=null`

The intent is a policy preview. It is not a Binance payload, not a signed request, and not a quantity instruction.

## No Binance Calls

R127 does not:

- place real orders
- create Binance order payloads
- call Binance order endpoints
- send signed requests
- call account or balance endpoints
- mutate `.env` files
- enable global live execution
- bypass R106/global gates
- create a live order endpoint
- implement real execution adapter behavior

Safety fields remain:

```json
{"order_placed":false,"real_order_placed":false,"execution_attempted":false,"order_payload_created":false,"network_allowed":false,"secrets_shown":false,"paper_live_separation_intact":true}
```

## CLI

Preview is the default and writes no ledger:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-autonomy-control-loop
```

Rejected recording example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-autonomy-control-loop \
  --record-decision \
  --confirm-decision-record "wrong"
```

Confirmed decision recording requires the exact phrase:

```text
I CONFIRM AUTONOMY DECISION RECORDING ONLY; NO ORDER; NO BINANCE CALL.
```

Supported flags:

- `--record-decision`
- `--lane-key <lane_key>`
- `--all-lanes`
- `--confirm-decision-record "<exact phrase>"`

## Decision Ledger

Confirmed recording appends `LANE_AUTONOMY_DECISION` records to:

```text
logs/hammer_radar_forward/lane_autonomy_decisions.ndjson
```

Preview and rejected recording do not write the ledger. Records include lane key, lane mode, candidate id, route status, autonomy decision, strategy intent, blockers, warnings, hard safety fields, and source surfaces used.

## Safety Constraints

R127 refuses decision recording when:

- confirmation is missing or invalid
- selected lane is not configured
- route source returns an error
- any source safety field reports order, execution, payload, network, or secrets
- paper/live separation is false
- strategy intent includes direct live quantity
- exit policy includes direct exchange payload

## Next Phases

- R128 lane autonomy scheduler: schedule R127 periodically in non-executing or paper-only mode with cadence and audit summary.
- R129 autonomous paper lane executor integration: wire R127 paper intents into the existing R125 paper-only executor.
- R130 first tiny-live autonomous lane authorization: explicit future authorization path for tiny-live autonomy review, still gated by R106/global safety.
