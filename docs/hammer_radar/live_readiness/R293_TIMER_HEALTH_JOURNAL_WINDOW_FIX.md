# R293 Timer Health Journal Window Fix

R293 fixes a false positive in the R292 dry-run timer health packet. It remains
read-only timer health only: no sudo, no systemd mutation, no `/etc` writes, no
Binance order/test-order/leverage/margin mutation endpoint, no live execution,
no executable payload, and no secrets.

## Why R292 Reported A False Positive

R292 fixed the repo-local systemd templates and added installed timer health, but
the health packet could scan too much journal history. After the operator
manually refreshed the installed unit files, old pre-refresh systemd warnings
such as `Invalid URL` could still appear in historical journal output. R292 then
reported `documentation_warning_seen=true` and
`installed_unit_refresh_required=true` even when the installed unit files had
already been fixed.

## R293 Behavior

Timer health now separates current health from stale history:

- `documentation_warning_seen` reflects only the current journal window.
- `documentation_warning_window` is `last_10_minutes`.
- `documentation_warning_window_seconds` is `600`.
- `current_journal_window_command` uses:

```bash
journalctl -u hammer-autonomous-trigger-scheduler-dry-run.service --since "10 minutes ago" --no-pager
```

- `stale_documentation_warning_seen` may report older `Invalid URL` warnings
  from the last 240 journal lines.
- `stale_documentation_warning_ignored_for_current_health=true` when stale
  warnings exist, the current window is clean, and the installed unit
  `Documentation=` lines are valid.

`installed_unit_refresh_required` is no longer inferred from stale journal
history. It is based on direct reads of:

```text
/etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.service
/etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.timer
```

If both installed unit files contain `Documentation=file:/...`, then
`installed_unit_refresh_required=false`.

## Expected Healthy Post-Refresh Values

After the operator has manually refreshed the installed dry-run timer/service
units and recent scheduler ticks are present, the expected healthy values are:

```json
{
  "status": "TIMER_HEALTH_ACTIVE",
  "timer_active": true,
  "recent_tick_seen": true,
  "documentation_warning_seen": false,
  "documentation_warning_window": "last_10_minutes",
  "documentation_warning_window_seconds": 600,
  "installed_unit_refresh_required": false,
  "stale_documentation_warning_seen": true,
  "stale_documentation_warning_ignored_for_current_health": true,
  "final_command_available": false,
  "submit_allowed": false,
  "real_order_forbidden": true
}
```

`stale_documentation_warning_seen` can also be `false` once old journal lines age
out. Either value is acceptable when `documentation_warning_seen=false`,
`installed_unit_refresh_required=false`, and the stale warning is ignored for
current health.

## Verification Commands

CLI:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-autonomous-trigger-scheduler-timer-health | jq .
```

API:

```bash
curl -sS http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/timer-health | jq .
```

Final console:

```bash
curl -sS http://127.0.0.1:8015/tiny-live/final-console | \
  jq '.autonomous_trigger_scheduler_timer_health_panel'
```

## Safety Invariants

- `codex_systemctl_mutation_performed=false`
- `codex_sudo_performed=false`
- `codex_install_performed=false`
- `dry_run_only=true`
- `live_execution_enabled=false`
- `per_signal_operator_approval_required=false`
- `final_command_available=false`
- `submit_allowed=false`
- `real_order_forbidden=true`
- no order placement
- no Binance order/test-order/leverage/margin mutation endpoint
- no executable order payload
- no secrets, signatures, signed URLs, API keys, or auth headers
