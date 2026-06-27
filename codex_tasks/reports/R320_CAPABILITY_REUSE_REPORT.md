# R320 Capability Reuse Report

## Phase Classification

- Primary classification: `DIAGNOSTIC / AUDIT`
- Secondary classification(s): `WIRING / INTEGRATION`
- Duplicate risk level: `MEDIUM`
- Reason: R320 adds a synthetic real-Telegram send drill preview that composes the existing R314 health payload, R315 alerting preview, R317 synthetic scenarios, and R318/R319 Telegram credential readiness. It does not create a sender, apply gate, systemd unit, order path, or credential store.

## Capability Scan

### Existing Docs Checked

- `README.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/PHASE_CAPABILITY_INDEX_R1_R100.md`
- `docs/hammer_radar/live_readiness/R314_MULTI_LANE_OBSERVATION_HEALTH_PANEL.md`
- `docs/hammer_radar/live_readiness/R315_MULTI_LANE_OBSERVATION_ALERTING_PREVIEW.md`
- `docs/hammer_radar/live_readiness/R316_HUMAN_REVIEWED_OBSERVATION_ALERT_SEND_GATE.md`
- `docs/hammer_radar/live_readiness/R317_OBSERVATION_ALERT_SEND_GATE_OPERATOR_DRILL.md`
- `docs/hammer_radar/live_readiness/R318_REAL_TELEGRAM_ALERT_SEND_GATE_PREVIEW.md`
- `docs/hammer_radar/live_readiness/R319_TELEGRAM_CREDENTIAL_READINESS_REPAIR.md`

### Existing Modules Checked

- `src/app/hammer_radar/operator/real_telegram_observation_alert_send_preview.py`
- `src/app/hammer_radar/operator/multi_lane_observation_alert_send_gate.py`
- `src/app/hammer_radar/operator/observation_alert_send_gate_operator_drill.py`
- `src/app/hammer_radar/operator/multi_lane_observation_alerting_preview.py`
- `src/app/hammer_radar/operator/multi_lane_observation_health_panel.py`
- `src/app/hammer_radar/operator/notification_watcher.py`
- `src/app/hammer_radar/operator/inspect.py`

### Existing Tests Checked

- `tests/hammer_radar/test_telegram_credential_readiness_repair.py`
- `tests/hammer_radar/test_real_telegram_observation_alert_send_preview.py`
- `tests/hammer_radar/test_observation_alert_send_gate_operator_drill.py`
- `tests/hammer_radar/test_multi_lane_observation_alert_send_gate.py`
- `tests/hammer_radar/test_multi_lane_observation_alerting_preview.py`
- `tests/hammer_radar/test_multi_lane_observation_health_panel.py`

### Existing Endpoints Checked

- Inspect CLI command: `multi-lane-observation-health-panel`
- Inspect CLI command: `multi-lane-observation-alerting-preview`
- Inspect CLI command: `multi-lane-observation-alert-send-gate`
- Inspect CLI command: `observation-alert-send-gate-operator-drill`
- Inspect CLI command: `real-telegram-observation-alert-send-preview`
- Operator notification surfaces listed in existing docs: `/notifications/status`, `/notifications/check`

### Existing CLI Commands Checked

- `PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview`
- `PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.observation_alert_send_gate_operator_drill`
- `PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect real-telegram-observation-alert-send-preview`
- `scripts/hammer_print_r319_telegram_credential_readiness_repair.sh`
- `scripts/hammer_print_r318_real_telegram_observation_alert_send_preview.sh`
- `scripts/hammer_print_r317_observation_alert_send_gate_operator_drill.sh`

### Existing Scheduler Tasks Checked

- R314/R315 observation timer status surfaces
- `hammer-multi-lane-dry-run-observation.timer`
- `hammer-paper-refresh.service`
- Telegram notification worker config surfaces from `notification_watcher.py`

### Existing Logs / Ledgers / Configs Checked

- `logs/hammer_radar_forward`
- `real_telegram_observation_alert_send_preview.ndjson`
- `observation_alert_send_gate_operator_drill.ndjson`
- `multi_lane_observation_alerting_preview.ndjson`
- `multi_lane_observation_health_panel.ndjson`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/autonomous_arming_state.json`
- private Telegram env-file reference: `/home/josue/.config/hammer-radar/notifications.env`

## Reuse / Extend / Create Decision

- Existing capability reused: R314 synthetic-compatible health payload shape, R315 alert severity/reason evaluation, R317 synthetic scenario construction, R318 real Telegram readiness preview, and R319 private env-file fallback.
- Existing capability extended: `src/app/hammer_radar/operator/inspect.py` now exposes `real-telegram-observation-alert-synthetic-send-drill-preview`.
- New capability created: R320 drill preview module, R320 operator print script, R320 documentation, R320 capability report, and R320 tests.
- Why new code was necessary: R320 needs a distinct drill ledger and scenario-level proof that real-send eligibility can be previewed for synthetic actionable alerts while keeping the actual real-send path inactive and non-executable.
- Why this is not duplicating prior work: The module does not implement a new Telegram sender or alert evaluator. It passes R317 synthetic health panels through R315 and then through the R318/R319 credential readiness and no-send boundary.

## Credentials Now Available Via Private Env File

R319 repaired the preview readiness path so that, when process env credentials are absent, the existing private env file can satisfy readiness:

```text
/home/josue/.config/hammer-radar/notifications.env
```

R320 reuses that loader path and reports only masked readiness fields. It does not write or mutate env files.

## Preview-Only Boundary

R320 emits these safety outcomes in every drill output:

```text
telegram_send_called=false
telegram_message_sent=false
real_telegram_send_called=false
real_telegram_message_sent=false
would_send_real_telegram_now=false
real_send_preview_only=true
```

The exact future phrase is reported for audit only:

```text
ENABLE REAL TELEGRAM OBSERVATION ALERT SEND
```

In R320 the phrase is inactive and non-executable.

## Synthetic Scenarios

- `healthy`: credentials are detected, `alert_required=false`, and healthy/no-heartbeat policy blocks any send-now path.
- `synthetic_stale_observation`: R317/R314-compatible stale observation input produces an actionable R315 alert preview and future real-send eligibility only after a future human-reviewed exact phrase path.
- `synthetic_final_safety_violation`: synthetic unsafe final-safety fields produce `CRITICAL_PREVIEW_NO_SEND`, with no send and no mutation in R320.

## Duplicate Risk Report

- Similar existing modules: `real_telegram_observation_alert_send_preview.py`, `observation_alert_send_gate_operator_drill.py`, `multi_lane_observation_alert_send_gate.py`
- Similar existing endpoints: inspect commands for R315, R316, R317, and R318
- Similar existing CLI commands: R317/R318/R319 print scripts
- Similar existing scheduler tasks: observation timer and Telegram notification worker surfaces
- Similar existing docs: R317, R318, and R319 live-readiness docs
- Risk: Medium, because the phase sits near both synthetic send-gate drills and real Telegram readiness.
- Mitigation: R320 composes those builders directly, keeps a separate ledger/event type for audit, and emits explicit no-send/no-mutation safety flags.

## Future R321 Path

If R320 remains clean, the recommended next phase is:

```text
R321 Human-Reviewed Real Telegram Synthetic Alert Send Apply Gate
```

That phase should prepare the first human-reviewed real-send apply gate, still requiring the exact phrase and operator action. Codex validation for that phase must still avoid sending real Telegram unless explicitly authorized by the future phase and operator.
