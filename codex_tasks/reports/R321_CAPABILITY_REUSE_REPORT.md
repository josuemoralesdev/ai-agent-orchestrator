# R321 Capability Reuse Report

## Phase Classification

Primary classification: WIRING / INTEGRATION

Secondary classification: DIAGNOSTIC / AUDIT

Duplicate risk level: MEDIUM

Reason: R321 is close to R316, R318, R319, and R320. It reuses their alert preview, synthetic scenario, credential readiness, and no-send safety boundaries instead of creating a new Telegram delivery path.

## Capability Scan Summary

Existing docs checked:

- `docs/hammer_radar/live_readiness/R320_REAL_TELEGRAM_OBSERVATION_ALERT_SYNTHETIC_SEND_DRILL_PREVIEW.md`
- `docs/hammer_radar/live_readiness/R319_TELEGRAM_CREDENTIAL_READINESS_REPAIR.md`
- `docs/hammer_radar/live_readiness/R318_REAL_TELEGRAM_ALERT_SEND_GATE_PREVIEW.md`
- `docs/hammer_radar/live_readiness/R317_OBSERVATION_ALERT_SEND_GATE_OPERATOR_DRILL.md`
- `docs/hammer_radar/live_readiness/R315_MULTI_LANE_OBSERVATION_ALERTING_PREVIEW.md`
- `docs/hammer_radar/PHASE_CAPABILITY_INDEX_R1_R100.md`

Existing modules checked:

- `src/app/hammer_radar/operator/real_telegram_observation_alert_synthetic_send_drill_preview.py`
- `src/app/hammer_radar/operator/real_telegram_observation_alert_send_preview.py`
- `src/app/hammer_radar/operator/multi_lane_observation_alert_send_gate.py`
- `src/app/hammer_radar/operator/observation_alert_send_gate_operator_drill.py`
- `src/app/hammer_radar/operator/multi_lane_observation_alerting_preview.py`
- `src/app/hammer_radar/operator/multi_lane_observation_health_panel.py`
- `src/app/hammer_radar/operator/notification_watcher.py`
- `src/app/hammer_radar/operator/inspect.py`

Existing tests checked:

- `tests/hammer_radar/test_real_telegram_observation_alert_synthetic_send_drill_preview.py`
- `tests/hammer_radar/test_telegram_credential_readiness_repair.py`
- `tests/hammer_radar/test_real_telegram_observation_alert_send_preview.py`
- `tests/hammer_radar/test_observation_alert_send_gate_operator_drill.py`
- `tests/hammer_radar/test_multi_lane_observation_alert_send_gate.py`
- `tests/hammer_radar/test_multi_lane_observation_alerting_preview.py`
- `tests/hammer_radar/test_multi_lane_observation_health_panel.py`

Existing endpoints checked:

- No FastAPI endpoint change was needed.
- The existing `inspect.py` CLI route pattern was extended with `real-telegram-synthetic-alert-send-apply-gate`.

Existing CLI commands checked:

- `multi-lane-observation-health-panel`
- `multi-lane-observation-alerting-preview`
- `multi-lane-observation-alert-send-gate`
- `observation-alert-send-gate-operator-drill`
- `real-telegram-observation-alert-send-preview`
- `real-telegram-observation-alert-synthetic-send-drill-preview`

Existing scheduler tasks checked:

- R314 health-panel timer status reads
- Multi-lane dry-run observation timer previews
- Paper refresh scheduler health summaries

Existing logs, ledgers, and configs checked:

- R314, R315, R316, R317, R318, and R320 NDJSON ledger naming patterns
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/autonomous_arming_state.json`
- private Telegram env-file fallback path documented by R319

## Reuse / Extend / Create Decision

Existing capability reused:

- R320 drill result shape and future-send eligibility language
- R319/R318 masked Telegram credential readiness
- R317 synthetic health scenarios
- R315 alert severity, reasons, message preview, and safety flags
- R316 confirmation and mock-send gate semantics
- `inspect.py` route pattern

Existing capability extended:

- The R318/R320 no-send real Telegram preview chain is extended with a human-reviewed apply gate.

New capability created:

- `src/app/hammer_radar/operator/real_telegram_synthetic_alert_send_apply_gate.py`
- `scripts/hammer_print_r321_real_telegram_synthetic_alert_send_apply_gate.sh`
- R321 docs and tests

Why new code was necessary:

- R320 intentionally kept the confirmation phrase inactive and non-executable. R321 needs a separate reviewed apply gate that can prove exact phrase handling and mock-send recording while still blocking real Telegram.

Why this is not duplicating prior work:

- R321 delegates synthetic scenario construction, alert preview, and credential readiness to existing modules. It only adds the apply boundary and the deliberately disabled real-send branch.

## R320 Drill Result Reuse

R321 reuses the R320 conclusion that:

- credentials are ready for future real send when readiness is valid
- synthetic stale-observation and final-safety scenarios are actionable
- healthy scenario is not sendable
- real Telegram send remains false during Codex validation

## Credential Readiness Reuse

Credential readiness is reused through `build_real_telegram_observation_alert_send_preview`, which uses R318/R319 logic:

- process env first
- private env-file fallback only when needed
- masked token and chat id previews only
- `secrets_shown=false`

## Notification Watcher Send Boundary

The real Telegram network boundary is `notification_watcher.send_telegram_message`.

R321 does not call this function. The only sender modes are:

- `mock`
- `real-disabled`

There is no R321 `real` mode.

## Confirmation Phrase

Exact phrase:

```text
ENABLE REAL TELEGRAM OBSERVATION ALERT SEND
```

Missing or wrong phrase blocks apply before any mock-send record. Exact phrase with `real-disabled` still blocks real send in Codex validation.

## Codex Validation Cannot Send

Codex validation cannot send because:

- no CLI `real` sender mode exists
- `real-disabled` returns `REAL_TELEGRAM_SYNTHETIC_SEND_GATE_REAL_SEND_DISABLED_IN_CODEX`
- `would_send_real_telegram_now=false`
- `real_telegram_send_called=false`
- `real_telegram_message_sent=false`
- the module does not call the Telegram network function

## Future Operator Action Boundary

R321 prepares the command shape only. A later R322 phase should produce an operator-run activation packet. That later phase must keep real-send disabled by default and require the operator to decide whether to run any real-send command.

## Duplicate Risks

Similar existing modules:

- R316 send gate
- R318 real Telegram preview
- R320 synthetic send drill preview

Similar existing endpoints:

- `inspect.py real-telegram-observation-alert-send-preview`
- `inspect.py real-telegram-observation-alert-synthetic-send-drill-preview`

Similar existing CLI commands:

- R316, R317, R318, R319, and R320 operator scripts

Similar existing scheduler tasks:

- None extended. Scheduler status is read-only through existing health-panel logic.

Similar existing docs:

- R317-R320 live-readiness docs

Risk:

- MEDIUM, because adding an apply gate near real Telegram delivery could accidentally create a real-send path.

Mitigation:

- R321 exposes no real sender mode, records real Telegram flags false, tests URL and Binance boundaries, and keeps all config/env/arming/systemd/live-order flags false.

## No-Live / No-Trade / No-Mutation Guarantees

R321 must preserve:

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
```
