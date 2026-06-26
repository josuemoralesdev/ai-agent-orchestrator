# R311 Capability Reuse Report

## Phase Classification

- Primary classification: `DIAGNOSTIC / AUDIT`
- Secondary classification: `WIRING / INTEGRATION`
- Duplicate risk level: `MEDIUM`
- Reason: R311 previews systemd timer wiring for an existing R310 dry-run observation scheduler. It resembles prior R289/R290/R292 dry-run timer work, but targets a distinct multi-lane observation command and does not create repo-local systemd template files.

## Existing Timer/Unit Naming Conventions

- Autonomous trigger dry-run templates use `hammer-autonomous-trigger-scheduler-dry-run.service` and `hammer-autonomous-trigger-scheduler-dry-run.timer`.
- Paper refresh uses `hammer-paper-refresh.service`.
- Operator service references include `hammer-approval-api.service`, `hammer-telegram-polling.service`, and `radar.service` in runbooks/status checks.
- R311 chosen preview names:
  - `hammer-multi-lane-dry-run-observation.service`
  - `hammer-multi-lane-dry-run-observation.timer`

## Existing Dry-Run Timer Health Conventions

- R292 timer health is read-only and uses `systemctl`/`journalctl` inspection only.
- R289/R290 separate repo templates, manual operator install, and timer health inspection.
- Installed-unit mutation fields stay explicit and false when Codex does not install/start/enable/reload units.
- R311 follows the same explicit false fields but is stricter: it does not write systemd template files under `ops/systemd` and does not call read-only systemctl health commands.

## Capability Scan

### Existing Docs Checked

- `docs/hammer_radar/live_readiness/R289_AUTONOMOUS_TRIGGER_SCHEDULER_SYSTEMD_INSTALL_CHECKLIST.md`
- `docs/hammer_radar/live_readiness/R290_MANUAL_SYSTEMD_DRY_RUN_TIMER_ACTIVATION_CHECKLIST.md`
- `docs/hammer_radar/live_readiness/R292_DRY_RUN_TIMER_OPERATIONAL_HARDENING.md`
- `docs/hammer_radar/live_readiness/R293_TIMER_HEALTH_JOURNAL_WINDOW_FIX.md`
- `docs/hammer_radar/live_readiness/R304_PAPER_REFRESH_DURABILITY_AND_STRATEGY_LAB_PREVIEW.md`
- `docs/hammer_radar/live_readiness/R310_MULTI_LANE_DRY_RUN_OBSERVATION_SCHEDULER.md`
- `docs/hammer_radar/R69_TELEGRAM_POLLING_RUNBOOK.md`
- `docs/hammer_radar/R74_POLICY_ARMING_RUNBOOK.md`
- `docs/hammer_radar/R76_FUNDED_TINY_LIVE_READINESS.md`
- `ops/systemd/README_hammer_paper_refresh.md`

### Existing Modules Checked

- `src/app/hammer_radar/operator/multi_lane_dry_run_observation_scheduler.py`
- `src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler.py`
- `src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler_timer_health.py`
- `src/app/hammer_radar/operator/inspect.py`
- `src/app/hammer_radar/operator/paper_refresh_scheduler.py`

### Existing Tests Checked

- `tests/hammer_radar/test_multi_lane_dry_run_observation_scheduler.py`
- `tests/hammer_radar/test_tiny_live_autonomous_trigger_scheduler.py`
- `tests/hammer_radar/test_paper_refresh_scheduler.py`
- `tests/hammer_radar/test_systemd_paper_refresh_service.py`
- `tests/hammer_radar/test_expansion_risk_contract_preview_repair.py`
- `tests/hammer_radar/test_eligible_lane_expansion_dry_run_preview.py`

### Existing Endpoints Checked

- Inspect CLI: `multi-lane-dry-run-observation`
- Inspect CLI: `tiny-live-autonomous-trigger-scheduler-systemd-template-status`
- Inspect CLI: `tiny-live-autonomous-trigger-scheduler-timer-health`
- Paper refresh API references: `/paper-refresh/status`, `/paper-refresh/run`, `/paper-refresh/runs`
- Final console safety reference: `/tiny-live/final-console`

### Existing CLI Commands Checked

- `multi-lane-dry-run-observation`
- `tiny-live-autonomous-trigger-scheduler-once`
- `tiny-live-autonomous-trigger-scheduler-loop`
- `tiny-live-autonomous-trigger-scheduler-systemd-template-status`
- `tiny-live-autonomous-trigger-scheduler-timer-health`
- `paper-refresh-status`
- `paper-refresh-run`
- `paper-refresh-runs`

### Existing Scheduler Tasks Checked

- R310 one-shot observation scheduler surface.
- R288 autonomous trigger scheduler dry-run loop.
- Paper refresh scheduler watch loop.

### Existing Logs/Ledgers/Configs Checked

- `logs/hammer_radar_forward/multi_lane_dry_run_observation.ndjson`
- `logs/hammer_radar_forward/tiny_live_autonomous_trigger_scheduler.ndjson`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/autonomous_arming_state.json`
- `ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template`
- `ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template`
- `ops/systemd/hammer-paper-refresh.service`
- `ops/systemd/hammer-telegram-operator-polling.service.example`

## Duplicate Risks

- Similar existing module: `tiny_live_autonomous_trigger_scheduler.py` has R289 systemd template status, but it is for autonomous trigger ticks, not multi-lane observation.
- Similar existing docs/scripts: R289/R290/R292 print/manual install workflows. R311 avoids duplicate install planning by stopping at a content preview and hash packet.
- Similar scheduler: R310 already performs the observation tick. R311 does not reimplement observation logic; it points systemd at the existing R310 `--once` command.
- Similar systemd files: existing templates under `ops/systemd/hammer-radar`. R311 does not add templates there to avoid implying install readiness.

## Chosen Unit/Timer Preview Design

- Service: `hammer-multi-lane-dry-run-observation.service`
- Timer: `hammer-multi-lane-dry-run-observation.timer`
- Working directory: `/home/josue/workspace/kernel/ai-agent-orchestrator-main`
- User: `josue`
- Command:

```text
/home/josue/workspace/kernel/ai-agent-orchestrator-main/.venv/bin/python -m src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler --log-dir /home/josue/workspace/kernel/ai-agent-orchestrator-main/logs/hammer_radar_forward --once
```

- Cadence:
  - `OnBootSec=2min`
  - `OnUnitActiveSec=60s`
  - `AccuracySec=10s`

## Why No Systemd Mutation Occurs

R311 only renders unit/timer text inside a JSON/text preview packet and appends the R311 ledger when requested. It does not write `/etc/systemd/system`, does not create repo-local unit template files, does not run `systemctl`, does not run `daemon-reload`, and does not install/enable/start any timer.

Future installation remains gated behind the inactive preview phrase:

```text
INSTALL MULTI LANE DRY RUN OBSERVATION TIMER
```

The phrase is deliberately `future_confirmation_phrase_active=false` and `future_confirmation_phrase_executable=false` in R311.
