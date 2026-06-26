# R314 Multi-Lane Observation Health Panel

## Why R314 Exists

R313 installed and enabled the real recurring observation timer:

```text
hammer-multi-lane-dry-run-observation.timer
```

The timer runs the R310 one-shot observation scheduler and the observation ledger is receiving rows. R314 gives the operator one compact health panel instead of raw lane packet JSON.

## What R313 Changed

R313 confirmed:

- timer enabled and active
- service executed the R310 `--once` command
- service exited successfully
- `multi_lane_dry_run_observation.ndjson` receives rows
- baseline lane remained `BTCUSDT|44m|long|ladder_close_50_618`
- no live order path became available

R314 does not install or modify that timer. It only inspects it.

## How To Run

Text panel:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_observation_health_panel --log-dir logs/hammer_radar_forward --text
```

JSON panel:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_observation_health_panel --log-dir logs/hammer_radar_forward --json
```

Inspect route:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward multi-lane-observation-health-panel
```

Operator script:

```bash
bash scripts/hammer_print_r314_multi_lane_observation_health_panel.sh
```

Output ledger:

```text
logs/hammer_radar_forward/multi_lane_observation_health_panel.ndjson
```

## How To Read The Panel

Sections:

- `HEALTH STATUS`: overall status, blockers, and recommended operator move.
- `TIMER`: systemd timer/service names, installed/enabled/active status, and last service exit status if available.
- `LAST TICK`: latest R310 observation timestamp, age, recency, observation ID, and source ledger.
- `LANES`: baseline lane, primary observed lanes, secondary watch-only lanes, and contract/status checks.
- `CANDIDATE VISIBILITY`: current candidate lane and whether it matches an observed lane.
- `FINAL LIVE SAFETY`: final gate status, blockers, real-order-forbidden state, submit availability, final command availability, armed lane, and timer health from final console when available.
- `PAPER REFRESH`: latest paper-refresh health and failed tasks.
- `SAFETY FLAGS`: locked no-live/no-submit/no-mutation fields.

The text output intentionally does not print full `lane_packets`.

## Health Status Meanings

`MULTI_LANE_OBSERVATION_HEALTH_OK` means:

- latest observation tick exists and is recent
- primary contracts are valid
- primary observation statuses are OK
- final live safety remains locked
- no fatal paper-refresh failure exists

`MULTI_LANE_OBSERVATION_HEALTH_DEGRADED` means:

- observation still looks safe, but an operator-visible repair may be needed
- common example: stale observation tick
- `eth_paper_outcome`-only paper refresh degradation is marked non-critical context

`MULTI_LANE_OBSERVATION_HEALTH_BLOCKED` means:

- required observation evidence is missing
- a primary lane contract/status is invalid
- final live safety unexpectedly allows submit/final command/real order
- a safety flag is not locked
- paper refresh has a critical failure

## What Not To Do

Do not use R314 to:

- place live orders
- call Binance order or test-order endpoints
- change leverage or margin
- enable live flags
- disable the kill switch
- arm or disarm lanes
- change the first Tiny Live lane
- write risk contracts
- write config or env files
- install, enable, start, stop, restart, or reload systemd units
- create or run a final command
- submit anything

R314 has no apply mode and no confirmation phrase.

## Recommended R315 Paths

If R314 is clean:

```text
R315 Multi-Lane Observation Alerting Preview
```

Add Telegram/operator notification previews only for degraded timer, stale observation, invalid contract, or safety-flag violation.

If R314 shows blockers:

```text
R315 Health Panel Repair
```
