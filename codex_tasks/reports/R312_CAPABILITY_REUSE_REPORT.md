# R312 Capability Reuse Report

## Phase Classification

- Primary classification: `WIRING / INTEGRATION`
- Secondary classification: `DIAGNOSTIC / AUDIT`
- Duplicate risk level: `MEDIUM`
- Reason: R312 adds a human-reviewed install gate for the R311 systemd preview. It resembles prior manual systemd install surfaces, but it targets the distinct R310 multi-lane dry-run observation timer and keeps real install behavior gated by an exact phrase.

## Capability Scan

### Existing Docs Checked

- `README.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R311_MULTI_LANE_DRY_RUN_TIMER_UNIT_PREVIEW.md`
- `docs/hammer_radar/live_readiness/R310_MULTI_LANE_DRY_RUN_OBSERVATION_SCHEDULER.md`
- `docs/hammer_radar/live_readiness/R290_MANUAL_SYSTEMD_DRY_RUN_TIMER_ACTIVATION_CHECKLIST.md`
- `docs/hammer_radar/PHASE_CAPABILITY_INDEX_R1_R100.md`
- `ops/systemd/README_hammer_paper_refresh.md`

### Existing Modules Checked

- `src/app/hammer_radar/operator/multi_lane_dry_run_timer_unit_preview.py`
- `src/app/hammer_radar/operator/multi_lane_dry_run_observation_scheduler.py`
- `src/app/hammer_radar/operator/inspect.py`
- `src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler.py`
- `src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler_timer_health.py`
- `src/app/hammer_radar/operator/expansion_risk_contract_human_reviewed_write_gate.py`

### Existing Tests Checked

- `tests/hammer_radar/test_multi_lane_dry_run_timer_unit_preview.py`
- `tests/hammer_radar/test_multi_lane_dry_run_observation_scheduler.py`
- `tests/hammer_radar/test_systemd_paper_refresh_service.py`
- `tests/hammer_radar/test_expansion_risk_contract_preview_repair.py`
- `tests/hammer_radar/test_eligible_lane_expansion_dry_run_preview.py`
- `tests/hammer_radar/test_paper_refresh_scheduler.py`

### Existing Endpoints Checked

- Inspect CLI route: `multi-lane-dry-run-observation`
- Inspect CLI route: `multi-lane-dry-run-timer-unit-preview`
- Inspect CLI route: `tiny-live-autonomous-trigger-scheduler-systemd-template-status`
- Final console safety reference: `/tiny-live/final-console`
- Paper refresh references: `/paper-refresh/status`, `/paper-refresh/run`, `/paper-refresh/runs`

### Existing CLI Commands Checked

- `multi-lane-dry-run-observation`
- `multi-lane-dry-run-timer-unit-preview`
- `tiny-live-autonomous-trigger-scheduler-once`
- `tiny-live-autonomous-trigger-scheduler-loop`
- `tiny-live-autonomous-trigger-scheduler-systemd-template-status`
- `paper-refresh-status`
- `paper-refresh-run`
- `paper-refresh-runs`

### Existing Scheduler Tasks Checked

- R310 one-shot multi-lane dry-run observation scheduler.
- R288/R290 autonomous trigger scheduler dry-run timer plan.
- Paper refresh scheduler watch loop.

### Existing Logs/Ledgers/Configs Checked

- `logs/hammer_radar_forward/multi_lane_dry_run_observation.ndjson`
- `logs/hammer_radar_forward/multi_lane_dry_run_timer_unit_preview.ndjson`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/autonomous_arming_state.json`
- `ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template`
- `ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template`
- `ops/systemd/hammer-paper-refresh.service`

## Existing Timer Install Patterns

- R289/R290 use print-only manual operator install plans for autonomous trigger dry-run systemd templates.
- R292 reads installed timer health with read-only `systemctl`/`journalctl` checks and preserves mutation flags.
- `ops/systemd/install_hammer_paper_refresh_service.sh` is a direct install script for paper refresh, but it calls `sudo install`, `systemctl daemon-reload`, and `systemctl enable`; R312 deliberately does not reuse that direct script shape.
- R309 human-reviewed write gate provides the closest confirmation-gated pattern: default preview, exact phrase required for mutation, explicit ledger, and safety fields.

## R311 Service Content

```ini
[Unit]
Description=Hammer Radar multi-lane dry-run observation tick
Documentation=file:/home/josue/workspace/kernel/ai-agent-orchestrator-main/docs/hammer_radar/live_readiness/R311_MULTI_LANE_DRY_RUN_TIMER_UNIT_PREVIEW.md
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=josue
WorkingDirectory=/home/josue/workspace/kernel/ai-agent-orchestrator-main
Environment=PYTHONPATH=.
Environment=HAMMER_RADAR_LOG_DIR=/home/josue/workspace/kernel/ai-agent-orchestrator-main/logs/hammer_radar_forward
Environment=HAMMER_LIVE_EXECUTION_ENABLED=false
Environment=HAMMER_ALLOW_LIVE_ORDERS=false
Environment=HAMMER_GLOBAL_KILL_SWITCH=true
ExecStart=/home/josue/workspace/kernel/ai-agent-orchestrator-main/.venv/bin/python -m src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler --log-dir /home/josue/workspace/kernel/ai-agent-orchestrator-main/logs/hammer_radar_forward --once
NoNewPrivileges=true
PrivateTmp=true
```

## R311 Timer Content

```ini
[Unit]
Description=Run Hammer Radar multi-lane dry-run observation every 60 seconds
Documentation=file:/home/josue/workspace/kernel/ai-agent-orchestrator-main/docs/hammer_radar/live_readiness/R311_MULTI_LANE_DRY_RUN_TIMER_UNIT_PREVIEW.md

[Timer]
OnBootSec=2min
OnUnitActiveSec=60s
AccuracySec=10s
Persistent=false
Unit=hammer-multi-lane-dry-run-observation.service

[Install]
WantedBy=timers.target
```

## Duplicate Risks

- Similar existing modules: R289/R290 autonomous trigger scheduler systemd surfaces, R292 timer health, R304 paper refresh durability, and the paper refresh install script.
- Similar endpoints: final console and timer-health panels mention systemd status, but they do not install the R310 multi-lane observation timer.
- Similar CLI commands: `multi-lane-dry-run-timer-unit-preview` already renders the content. R312 reuses it instead of duplicating service/timer generation.
- Similar scheduler tasks: R310 already performs the observation tick. R312 never reimplements observation logic.
- Risk: creating a second install pathway could imply live readiness or bypass operator review.
- Mitigation: R312 defaults to preview-only, requires `INSTALL MULTI LANE DRY RUN OBSERVATION TIMER`, supports mock systemctl for tests, and keeps live/order/arming/config/env safety fields locked.

## Selected Guarded Install Implementation Path

- Create `src/app/hammer_radar/operator/multi_lane_dry_run_timer_install_gate.py`.
- Reuse R311 rendered service/timer content and hashes.
- Default CLI behavior renders install paths and intended systemctl actions, appends a gate ledger, and writes no systemd files.
- Apply mode requires `--apply` and exact `--confirmation`.
- Apply writes only the service and timer to the selected `--install-dir`, creates backups for existing files, and records files written.
- `--systemctl-mode mock` records `daemon-reload`, `enable`, and `start` calls without executing them.
- `--systemctl-mode real` exists for a future human-operated phase only and still requires apply plus exact confirmation.

## Why R312 Still Does Not Trade Or Arm Lanes

R312 installs or previews only a systemd wrapper around the existing R310 `--once` observation command. R310 records multi-lane dry-run observation packets only. It does not create executable payloads, submit orders, call Binance order/test-order/leverage/margin endpoints, mutate risk contracts, mutate arming state, alter live flags, write env files, or disable the kill switch. R312 adds no trading connector calls and no arming path.
