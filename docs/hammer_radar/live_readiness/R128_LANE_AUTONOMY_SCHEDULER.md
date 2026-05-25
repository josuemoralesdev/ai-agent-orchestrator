# R128 Lane Autonomy Scheduler

Phase: R128

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: EXTENSION OF EXISTING CAPABILITY, DIAGNOSTIC / AUDIT
- Duplicate risk level: HIGH

## What R128 Adds

R128 adds a non-executing scheduler scaffold for the R127 lane autonomy control loop:

```text
src/app/hammer_radar/operator/lane_autonomy_scheduler.py
```

The scheduler runs one lane-autonomy tick on demand, summarizes the R127 decisions, and can append an audit tick only after exact scheduler-record confirmation.

The scheduler ledger is:

```text
logs/hammer_radar_forward/lane_autonomy_scheduler_ticks.ndjson
```

## Why Scheduling Is Next

R127 moved fast-lane decisions from stale per-signal approval into a non-executing autonomy loop. R128 turns that loop into a repeatable scheduler surface so Hammer Radar can periodically inspect fresh routed candidates, lane modes, entry intent, risk intent, stop/take-profit intent, cooldowns, daily limits, and ledger state.

This is the next step toward fully automated lane trading because the operator arms lanes and strategy scope ahead of time, while the machine repeatedly evaluates fresh conditions. R128 still stops at audit and decision recording. It does not execute.

## Preview Mode

Preview is the default:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-autonomy-scheduler
```

Preview returns `LANE_AUTONOMY_SCHEDULER_PREVIEW`.

Preview does not write:

- scheduler tick records
- R127 decision records
- paper execution records
- order payloads

## Record-Tick Mode

Confirmed tick recording requires:

```text
I CONFIRM AUTONOMY SCHEDULER RECORDING ONLY; NO ORDER; NO BINANCE CALL.
```

Example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-autonomy-scheduler \
  --record-tick \
  --confirm-scheduler-record "I CONFIRM AUTONOMY SCHEDULER RECORDING ONLY; NO ORDER; NO BINANCE CALL."
```

If the phrase is missing or wrong, R128 returns `LANE_AUTONOMY_SCHEDULER_REJECTED` and writes nothing.

## Record-Decisions Behavior

`--record-decisions` may be used with a confirmed scheduler run to delegate decision recording to R127. R128 uses the existing R127 decision-recording function and R127 safety checks rather than duplicating lane/router logic.

R128 refuses recording when:

- confirmation is invalid
- selected lane is not configured
- route source errors occur
- any source safety field reports order, execution, payload, network, or secrets
- paper/live separation is false
- a decision would imply a direct order payload

## Why No Real Orders Occur

R128 does not:

- place real orders
- create Binance order payloads
- call Binance order endpoints
- send signed requests
- call account or balance endpoints
- mutate `.env` files
- enable global live execution
- bypass R106/global gates
- install or start systemd services
- create a live order endpoint
- implement execution adapter behavior

Scheduler safety fields remain:

```json
{"order_placed":false,"real_order_placed":false,"execution_attempted":false,"order_payload_created":false,"network_allowed":false,"secrets_shown":false,"paper_live_separation_intact":true}
```

## Manual Scheduling Notes

R128 is CLI-only. Operators may later wrap the command in manual cron or systemd, but this phase does not install, enable, or start services.

Suggested future cron shape for review only:

```cron
*/5 * * * * cd /path/to/repo && PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward lane-autonomy-scheduler
```

Use confirmed recording only after reviewing local safety and ledger behavior.

## Optional Systemd Template

Docs-only systemd guidance is in:

```text
docs/hammer_radar/live_readiness/R128_SYSTEMD_TEMPLATE_NOT_INSTALLED.md
```

It is not installed, not enabled, and must not be copied blindly.

## Next Phases

- R129 autonomous paper lane executor integration: connect confirmed scheduler mode to the existing R125 paper-only lane executor.
- R130 first tiny-live autonomous lane authorization: design explicit future authorization for tiny-live autonomous lanes while keeping R106/global gates authoritative.
