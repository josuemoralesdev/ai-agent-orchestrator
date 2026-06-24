# R304 Paper Refresh Durability And Strategy Lab Preview

R304 hardens the paper refresh watcher and adds a read-only Strategy Lab preview.

## What Changed

- Paper refresh task records now include task name, status, recoverability, exception class, sanitized error message, duration, `live_execution_enabled=false`, and `order_placed=false`.
- One non-critical paper-side task failure now records `PAPER_REFRESH_DEGRADED_NON_CRITICAL` and the watch loop continues.
- Repeated critical task failures now stop the watcher with a nonzero exit code so `Restart=on-failure` can work.
- Watcher journal lines now include failed task names and health:

```text
paper_refresh run_id=<id> completed=<n> failed=<n> failed_tasks=<names> health=<status> order_placed=false
```

- Strategy Lab preview writes:

```text
logs/hammer_radar_forward/strategy_lab_preview.ndjson
```

## Why Paper Refresh Was Silently Dying

`hammer-paper-refresh.service` already had `Restart=on-failure`, but the Python watcher returned success after `max_errors`. Systemd saw status `0/SUCCESS`, so it did not restart the service.

R304 changes the watcher so only critical repeated failures trip max-errors, and that path returns nonzero.

## How To Validate

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/hammer_radar/test_paper_refresh_scheduler.py tests/hammer_radar/test_strategy_lab_preview.py -q
PYTHONPATH=. .venv/bin/python -m pytest tests/hammer_radar/test_*paper* tests/hammer_radar/test_*strategy* tests/hammer_radar/test_*betrayal* -q
PYTHONPATH=. .venv/bin/python -m pytest tests/hammer_radar -q
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_preview --help
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_preview --log-dir logs/hammer_radar_forward
bash scripts/hammer_print_r304_strategy_lab_and_refresh_health.sh
curl -s http://127.0.0.1:8015/tiny-live/final-console | jq .
curl -s http://127.0.0.1:8015/tiny-live/final-authorization-gate/status | jq .
```

## Reading Strategy Lab Preview

Each candidate includes:

- `watch_category`: `LIVE_QUALIFIED`, `NEAR_MISS_INCUBATOR`, `PAPER_ONLY`, `BETRAYAL_INVERSE_PREVIEW`, or `BLOCKED`
- evidence metrics: sample count, win rate, average PnL, total PnL, fill rate, stop rate
- freshness status for the current candidate, if present
- source chain and evidence files
- risk-contract compatibility preview
- blockers
- `recommended_lab_action`

Every candidate remains preview-only:

```text
live_allowed=false
final_command_available=false
submit_allowed=false
real_order_forbidden=true
```

## Betrayal / Inverse Preview

Betrayal candidates remain blocked from Tiny Live in R304. The preview gate can output:

- `BETRAYAL_BLOCKED_PREVIEW_ONLY`
- `BETRAYAL_PROMOTION_CANDIDATE_FOR_FUTURE_REVIEW`
- `BETRAYAL_REJECTED`

It never outputs live permission.

## What Not To Do

- Do not promote Strategy Lab rows to Tiny Live from R304 output.
- Do not broaden the armed lane from this phase.
- Do not disable the kill switch.
- Do not enable live execution flags.
- Do not run Binance order, test-order, leverage, or margin mutation endpoints.
- Do not treat `EXPANSION_PREVIEW_ONLY` as approval.

## Systemd Note

No installed systemd unit is changed by R304. The existing `ops/systemd/hammer-paper-refresh.service` already uses:

```text
Restart=on-failure
```

After R304, critical max-errors exits nonzero, so the existing policy can restart it. Refresh installed units manually only after operator review.

## Future R305 Recommendation

Recommended R305 path: Strategy Lab Variant Test Pack.

Focus on entry, timing, TP, SL, trailing, RSI, regime, and betrayal variants for near-miss lanes. Keep it dry-run/paper-only and do not mutate live execution.
