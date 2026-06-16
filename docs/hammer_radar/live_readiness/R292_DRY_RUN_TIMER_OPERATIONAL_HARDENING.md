# R292 Dry-Run Timer Operational Hardening

R292 hardens visibility for the already manually installed autonomous trigger
scheduler dry-run timer. It does not install, reload, start, stop, enable, or
disable any systemd unit from Codex.

## What Changed

- Repo-local service and timer templates now use absolute `file:` URLs in
  `Documentation=`.
- A read-only timer health packet is available from:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-autonomous-trigger-scheduler-timer-health
```

- The Approval API exposes:

```text
GET /tiny-live/autonomous-trigger-scheduler/timer-health
```

- The final console includes `autonomous_trigger_scheduler_timer_health_panel`.
- `scripts/hammer_print_r292_refresh_installed_dry_run_timer_units.sh` prints the
  manual refresh plan only.

## Why The Documentation Warning Happened

The installed timer was created from templates whose `Documentation=` value was a
repo-relative Markdown path. systemd expects a valid documentation URI, such as a
`file:` URL. The repo templates now use absolute file URLs, but already installed
unit files will keep the old value until the operator manually refreshes them.

## Manual Refresh After Commit

Print and review the refresh plan:

```bash
bash scripts/hammer_print_r292_refresh_installed_dry_run_timer_units.sh
```

The script prints backup, manual stop, install, daemon-reload, start, status,
timer, journal, and rollback commands. It does not execute them.

## Verify Timer Health

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

## Rollback

Use the rollback section printed by:

```bash
bash scripts/hammer_print_r292_refresh_installed_dry_run_timer_units.sh
```

Rollback restores the unit files from the printed `/tmp/hammer-r292-systemd-backup`
backup path. It remains a manual operator action. Codex does not mutate
`/etc/systemd/system`.

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
- no Binance trade-submit or validation endpoint
- no leverage or margin mutation endpoint
- no executable order payload
- no secrets, signatures, signed URLs, API keys, or auth headers
