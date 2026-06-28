# R322 Capability Reuse Report

## Phase Classification

Primary classification: DIAGNOSTIC / AUDIT

Secondary classification: WIRING / INTEGRATION

Duplicate risk level: MEDIUM

Reason: R322 resembles the R318-R321 Telegram readiness and synthetic send proof surfaces. It does not implement real-send execution; it reuses R321 to produce an operator packet.

## Capability Scan

Existing docs checked:

- `README.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R321_HUMAN_REVIEWED_REAL_TELEGRAM_SYNTHETIC_ALERT_SEND_APPLY_GATE.md`
- `docs/hammer_radar/live_readiness/R320_REAL_TELEGRAM_OBSERVATION_ALERT_SYNTHETIC_SEND_DRILL_PREVIEW.md`
- `docs/hammer_radar/live_readiness/R319_TELEGRAM_CREDENTIAL_READINESS_REPAIR.md`
- `docs/hammer_radar/PHASE_CAPABILITY_INDEX_R1_R100.md`

Existing modules checked:

- `src/app/hammer_radar/operator/real_telegram_synthetic_alert_send_apply_gate.py`
- `src/app/hammer_radar/operator/real_telegram_observation_alert_synthetic_send_drill_preview.py`
- `src/app/hammer_radar/operator/real_telegram_observation_alert_send_preview.py`
- `src/app/hammer_radar/operator/notification_watcher.py`
- `src/app/hammer_radar/operator/inspect.py`

Existing tests checked:

- `tests/hammer_radar/test_real_telegram_synthetic_alert_send_apply_gate.py`
- `tests/hammer_radar/test_real_telegram_observation_alert_synthetic_send_drill_preview.py`
- `tests/hammer_radar/test_telegram_credential_readiness_repair.py`

Existing endpoints checked:

- local inspect CLI route `real-telegram-observation-alert-send-preview`
- local inspect CLI route `real-telegram-observation-alert-synthetic-send-drill-preview`
- local inspect CLI route `real-telegram-synthetic-alert-send-apply-gate`
- final console smoke target `/tiny-live/final-console`

Existing CLI commands checked:

- `real-telegram-observation-alert-send-preview`
- `real-telegram-observation-alert-synthetic-send-drill-preview`
- `real-telegram-synthetic-alert-send-apply-gate`
- `notification-status`
- `notification-check`

Existing scheduler tasks checked:

- multi-lane dry-run observation timer preview/install gate references
- paper refresh scheduler references
- no scheduler start path is used by R322

Existing logs/ledgers/configs checked:

- `real_telegram_synthetic_alert_send_apply_gate.ndjson`
- `real_telegram_observation_alert_synthetic_send_drill_preview.ndjson`
- `real_telegram_observation_alert_send_preview.ndjson`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/autonomous_arming_state.json`

## Reuse / Extend / Create Decision

Existing capability reused: R321 apply gate, R320 synthetic drill semantics, R318 masked Telegram readiness, R315/R314 safety fields.

Existing capability extended: inspect CLI wiring adds a R322 packet route.

New capability created: `real_telegram_synthetic_alert_activation_packet.py` and the R322 operator print script.

Why new code was necessary: R321 prepares an apply gate and records proof statuses. R322 needs a separate operator-facing activation packet that aggregates those proofs and separates safe preview, mock apply, real-disabled, and manual-only real-send status.

Why this is not duplicating prior work: R322 does not create another sender, another preview policy, or another credential loader. It composes existing R321 proof calls and emits a packet.

## R321 Apply Gate Reuse

R322 calls the R321 gate in four no-write proof paths:

- default preview
- wrong phrase apply block
- exact phrase plus mock apply
- exact phrase plus real-disabled apply

The packet is ready only when those proof paths match expected statuses and all real Telegram flags remain false.

## Why R322 Is Not Real-Send Execution

R322 is an operator packet, not an implementation of real-send execution. R321 exposes only `mock` and `real-disabled`. R322 does not add `real`, does not call `notification_watcher.send_telegram_message`, and does not make a runnable real-send command.

## Credential Readiness Source

Credential readiness comes from the existing R318/R321 masked readiness path. If process env lacks Telegram credentials, R318 can read the private operator env file:

```text
/home/josue/.config/hammer-radar/notifications.env
```

R322 reports only presence, source kind, source path presence, and masked previews.

## Exact Real-Send Command Shape

Current code has no executable real-send command. The R322 packet reports:

```text
not_available_in_current_code_r321_has_no_real_sender_mode
```

Any future real-send command requires a separate tiny operator patch and must remain manually reviewed.

## No-Secret Policy

R322 must not print raw tokens, full chat ids, auth headers, `.env` values, or credential-derived raw material. JSON and text output use the existing masked readiness fields only.

## No-Live / No-Trade / No-Mutation Guarantees

R322 preserves:

- `live_execution_enabled=false`
- `allow_live_orders=false`
- `global_kill_switch=true`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `submit_allowed=false`
- `final_command_available=false`
- `real_order_forbidden=true`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `leverage_change_called=false`
- `margin_change_called=false`
- `secrets_shown=false`
- `paper_live_separation_intact=true`
- `autonomous_arming_state_changed=false`
- `global_live_flags_changed=false`
- `risk_contract_config_mutated=false`
- `config_written=false`
- `env_written=false`
- `env_mutated=false`
- `systemd_unit_mutated=false`
- `scheduler_started=false`
- `telegram_send_called=false`
- `telegram_message_sent=false`
- `real_telegram_send_called=false`
- `real_telegram_message_sent=false`

## Duplicate Risk Report

Similar existing modules:

- `real_telegram_synthetic_alert_send_apply_gate.py`
- `real_telegram_observation_alert_synthetic_send_drill_preview.py`
- `real_telegram_observation_alert_send_preview.py`

Similar existing endpoints:

- inspect routes for R318, R320, and R321

Similar existing CLI commands:

- R318 preview CLI
- R320 synthetic drill CLI
- R321 apply gate CLI

Similar existing scheduler tasks:

- none; R322 does not start or install scheduler tasks

Similar existing docs:

- R320 and R321 live-readiness docs

Risk: MEDIUM because this phase is near the real Telegram send boundary.

Mitigation: reuse R321 proof paths, no real sender mode, no Telegram API call, no secret printing, no config/env/systemd mutation, no live order path.

## Strategy Lab Return Recommendation

After Telegram completion, return to:

- more lanes
- more entry modes
- more strategy variants
- more candidate surface
- Tiny Live signal readiness

Recommended next phase:

```text
R323 Strategy Lab Expansion Re-entry and Candidate Surface Map
```
