# R319 Capability Reuse Report

## Phase Classification

- Primary classification: `DIAGNOSTIC / AUDIT`
- Secondary classification(s): `WIRING / INTEGRATION`
- Duplicate risk level: `MEDIUM`
- Reason: R319 extends the existing R318 real Telegram send gate preview with safe credential-source resolution for the existing private systemd `EnvironmentFile`. It does not create a new sender, credential store, systemd service, or live-trading path.

## Capability Scan

### Existing Docs Checked

- `README.md`
- `docs/hammer_radar/R69_TELEGRAM_POLLING_RUNBOOK.md`
- `docs/hammer_radar/PHASE_CAPABILITY_INDEX_R1_R100.md`
- `docs/hammer_radar/live_readiness/R317_OBSERVATION_ALERT_SEND_GATE_OPERATOR_DRILL.md`
- `docs/hammer_radar/live_readiness/R318_REAL_TELEGRAM_ALERT_SEND_GATE_PREVIEW.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `deploy/systemd/hammer-telegram-polling.service`
- `ops/systemd/hammer-telegram-operator-polling.service.example`

### Existing Modules Checked

- `src/app/hammer_radar/operator/real_telegram_observation_alert_send_preview.py`
- `src/app/hammer_radar/operator/notification_watcher.py`
- `src/app/hammer_radar/operator/telegram_operator_bridge.py`
- `src/app/hammer_radar/operator/telegram_polling_worker.py`
- `src/app/hammer_radar/operator/telegram_approval_challenge.py`
- `src/app/hammer_radar/operator/inspect.py`

### Existing Tests Checked

- `tests/hammer_radar/test_real_telegram_observation_alert_send_preview.py`
- `tests/hammer_radar/test_telegram_polling_worker.py`
- `tests/hammer_radar/test_telegram_operator_bridge.py`
- `tests/hammer_radar/test_notification_watcher.py`
- observation alert/send gate tests listed in the R319 validation command

### Existing Endpoints Checked

- Inspect CLI command: `real-telegram-observation-alert-send-preview`
- Existing notification surfaces from capability index: `/notifications/status`, `/notifications/check`
- Existing Telegram surfaces from capability index: `/telegram/operator-command`, `/telegram/polling/status`

### Existing CLI Commands Checked

- `PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview`
- `PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect real-telegram-observation-alert-send-preview`
- `scripts/hammer_print_r318_real_telegram_observation_alert_send_preview.sh`

### Existing Scheduler Tasks Checked

- `hammer-telegram-polling.service`
- `hammer-telegram-operator-polling.service.example`
- Required R319 safety status checks for `hammer-multi-lane-dry-run-observation.timer` and `hammer-paper-refresh.service`

### Existing Logs / Ledgers / Configs Checked

- `logs/hammer_radar_forward`
- R318 ledger name: `real_telegram_observation_alert_send_preview.ndjson`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/autonomous_arming_state.json`
- private systemd env-file reference: `/home/josue/.config/hammer-radar/notifications.env`

## Exact Expected Environment / Config Variable Names

The existing loader is `load_notification_config` in `src/app/hammer_radar/operator/notification_watcher.py`.

It reads:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `HAMMER_ALERT_TELEGRAM_ENABLED`
- `HAMMER_ALERT_MIN_INTERVAL_SECONDS`
- `HAMMER_ALERT_POLL_SECONDS`
- `HAMMER_ALERT_REQUIRE_DRY_RUN_VALID`
- `HAMMER_ALERT_REQUIRE_PROPOSED_TICKET`
- `HAMMER_ALERT_SYSTEM_STILL_BLOCKED_ENABLED`
- `HAMMER_ALERT_ACTIONABLE_PAPER_ENABLED`
- `HAMMER_ALERT_ACTIONABLE_PAPER_MIN_SCORE`
- `HAMMER_ALERT_EXPIRING_SOON_MINUTES`
- `HAMMER_ALERT_EXPIRED_MISSED_RECORD_ENABLED`

Only `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are required for future Telegram send credential readiness. `HAMMER_ALERT_TELEGRAM_ENABLED` controls the notification worker path and is not itself a credential.

## Where Existing Loader Reads From

`load_notification_config(env=None)` reads from `os.environ`. Tests and previews may pass an injected `env` mapping so readiness can be evaluated without mutating the real process environment.

The systemd examples use an `EnvironmentFile` outside the repo:

```text
/home/josue/.config/hammer-radar/notifications.env
```

R319 keeps process env precedence and, only when one or both Telegram credentials are missing, reads that private env file for `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Test coverage injects a temporary env-file path so tests do not touch real operator secrets.

## Masking Policy

R319 preserves the existing R318 masking policy:

- missing values print `missing`
- values of eight characters or fewer print `present_masked`
- longer values print only a four-character prefix and four-character suffix
- full token and full chat id values are never included in payloads, text output, reports, docs, or scripts
- `telegram_config_source_kind=private_env_file` and `telegram_config_source_path_present=true` identify the fallback without exposing credential values
- `secrets_shown=false` is emitted in the readiness object and safety flags

## Current Blocker Cause

R318 validation showed:

- `telegram_token_present=false`
- `telegram_chat_id_present=false`
- `real_send_available_for_future=false`
- `real_send_blockers=["telegram_token_missing","telegram_chat_id_missing"]`

The cause was missing `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in the interactive shell environment visible to `load_notification_config`, even though the systemd `EnvironmentFile` already contained them.

## Operator Repair Instructions

1. Put credentials in a private operator env file outside the repo, such as `/home/josue/.config/hammer-radar/notifications.env`.
2. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` there.
3. Optionally set `HAMMER_ALERT_TELEGRAM_ENABLED=true` for the notification worker path.
4. Do not paste credentials into shell commands, git-tracked files, logs, screenshots, or tickets.
5. Re-run R319 readiness commands and confirm only masked previews appear.

## Reuse / Extend / Create Decision

- Existing capability reused: R318 real Telegram observation alert send preview, notification config loader, inspect command, existing masking helper, existing no-send safety fields.
- Existing capability extended: R318 preview payload now includes a nested `telegram_config_readiness` object while preserving flat R318 fields, and resolves missing credentials from the existing private systemd env file.
- New capability created: R319 operator print script, R319 docs, R319 capability report, and focused R319 tests.
- Why new code was necessary: JSON readiness previously lacked the nested object requested for consistent machine inspection, and the preview could not see credentials available to systemd through the private operator env file.
- Why this is not duplicating prior work: The implementation does not create a second sender or credential store. It parses only the existing private env file for the two Telegram credential names, then still uses `load_notification_config` to build the config object.

## Duplicate Risk Report

- Similar existing modules: `notification_watcher.py`, `real_telegram_observation_alert_send_preview.py`, `telegram_polling_worker.py`
- Similar existing endpoints: `/notifications/status`, `/notifications/check`, `/telegram/polling/status`, inspect command `real-telegram-observation-alert-send-preview`
- Similar existing CLI commands: R318 preview CLI and script
- Similar existing scheduler tasks: Telegram polling systemd examples
- Similar existing docs: R69 Telegram polling runbook, R318 real Telegram alert send gate preview
- Risk: Medium, because Telegram credential status already appears in notification and R318 surfaces.
- Mitigation: Reused `load_notification_config` and the R318 builder; added only source resolution, nested readiness output, docs, a no-write print script, and tests.

## Why R319 Does Not Send Or Mutate Secrets

- The R319 script calls the preview CLI with `--no-write`.
- No sender function is invoked by the R318/R319 preview path.
- No env files are written.
- No repo config files are written by the readiness code.
- No systemd commands are executed by the script or module.
- No Telegram token or full chat id is printed.
- No live order, submit, final command, Binance endpoint, leverage change, or margin change is available in this phase.

## Required Safety Fields

```text
live_execution_enabled=false
allow_live_orders=false
global_kill_switch=true
order_placed=false
real_order_placed=false
execution_attempted=false
submit_allowed=false
final_command_available=false
real_order_forbidden=true
binance_order_endpoint_called=false
binance_test_order_endpoint_called=false
leverage_change_called=false
margin_change_called=false
secrets_shown=false
paper_live_separation_intact=true
autonomous_arming_state_changed=false
global_live_flags_changed=false
risk_contract_config_mutated=false
config_written=false
env_written=false
env_mutated=false
systemd_unit_mutated=false
scheduler_started=false
telegram_send_called=false
telegram_message_sent=false
real_telegram_send_called=false
real_telegram_message_sent=false
```
