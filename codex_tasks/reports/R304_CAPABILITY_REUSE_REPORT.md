# R304 Capability Reuse Report

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classifications: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: MEDIUM
- Reason: paper refresh, promotion watch, tiny-live gates, and betrayal previews already exist; R304 extends/wires them rather than adding execution authority.

## Existing Reusable Modules

- `src/app/hammer_radar/operator/paper_refresh_scheduler.py`: existing paper/watch refresh scheduler, task list, run ledger, CLI/API status surface.
- `src/app/hammer_radar/operator/strategy_promotion_watcher.py`: existing live-qualified, near-miss, paper-only lane classification and fresh candidate watcher.
- `src/app/hammer_radar/operator/tiny_live_strategy_lane_selection.py`: lane key builder, exact lane strategy qualification, and risk-contract compatibility preview.
- `src/app/hammer_radar/operator/tiny_live_fresh_trigger_watch.py`: current candidate freshness and final-command safety defaults.
- `src/app/hammer_radar/operator/tiny_live_final_authorization_gate.py`: final wait/ready/blocked status surface with current Tiny Live lane context.
- `src/app/hammer_radar/operator/tiny_live_final_console.py`: operator final-console composition and existing safety panels.
- `src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler.py`: dry-run scheduler pattern and safety flags.
- `src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler_timer_health.py`: read-only systemd timer health inspection.
- `src/app/hammer_radar/operator/tiny_live_risk_contract.py`: local non-secret risk config reader.
- `src/app/hammer_radar/operator/tiny_live_risk_contract_validation.py`: risk-contract validation and 10x/80 USDT cap interpretation.
- `src/app/hammer_radar/operator/betrayal_paper_outcome_ledger.py`: betrayal true-paper evidence summaries.
- `src/app/hammer_radar/operator/betrayal_*`: existing betrayal audit, inverse validation, source, shadow, and true-paper tracking surfaces.

## Existing Endpoints / CLI Surfaces

- `/paper-refresh/status`, `/paper-refresh/run`, `/paper-refresh/runs`
- `/tiny-live/final-console`
- `/tiny-live/final-authorization-gate/status`
- `python -m src.app.hammer_radar.operator.inspect paper-refresh-status`
- `python -m src.app.hammer_radar.operator.inspect paper-refresh-run`
- `python -m src.app.hammer_radar.operator.inspect paper-refresh-runs`
- `python -m src.app.hammer_radar.operator.inspect tiny-live-final-authorization-gate`
- `python -m src.app.hammer_radar.operator.inspect tiny-live-autonomous-trigger-scheduler-timer-health`
- Betrayal preview/audit CLI surfaces including `betrayal-inverse-validation`, `betrayal-strategy-audit`, and betrayal paper ledger surfaces.

## Existing Log Files

- `logs/hammer_radar_forward/paper_refresh_runs.ndjson`
- `logs/hammer_radar_forward/strategy_promotion_status.ndjson`
- `logs/hammer_radar_forward/strategy_promotion_events.ndjson`
- `logs/hammer_radar_forward/strategy_performance.ndjson`
- `logs/hammer_radar_forward/signals.ndjson`
- `logs/hammer_radar_forward/outcomes.ndjson`
- `logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson`
- `logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson`
- `logs/hammer_radar_forward/tiny_live_final_authorization_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_autonomous_trigger_scheduler.ndjson`

## Configs / Systemd Checked

- `configs/hammer_radar/autonomous_arming_state.json`: current armed dry-run lane remains `BTCUSDT|44m|long|ladder_close_50_618`; `live_execution_enabled=false`.
- `configs/hammer_radar/tiny_live_risk_contracts.json`: existing local contracts only; no R304 mutation.
- `ops/systemd/hammer-paper-refresh.service`: already uses `Restart=on-failure`; Python watcher needed nonzero critical-max-errors behavior.
- `ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template`
- `ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template`

## Duplicate Risks

- Strategy Lab could duplicate `strategy_promotion_watcher.py`.
- Betrayal/inverse lab preview could duplicate betrayal ranking/feed previews.
- Paper refresh health could duplicate `/paper-refresh/runs`.
- Operator script could duplicate final-console panels.

## Chosen Extension Points

- Extended `paper_refresh_scheduler.py` in place for task durability and failure visibility.
- Added `strategy_lab_preview.py` only as a read-only compositor because no existing module produced the requested all-lane lab packet with betrayal gate preview and `strategy_lab_preview.ndjson`.
- Wired the Strategy Lab preview into `inspect.py` using the existing operator CLI pattern.
- Added `scripts/hammer_print_r304_strategy_lab_and_refresh_health.sh` as a read-only local summary script.

## Reuse / Extend / Create Decision

- Existing capability reused: paper refresh scheduler, strategy promotion watcher, lane selection, risk-contract validation, fresh trigger watch, final authorization gate, timer health, betrayal paper ledger.
- Existing capability extended: paper refresh scheduler task accounting, health status, and watch-loop stop semantics.
- New capability created: `strategy_lab_preview.py` as a paper-only integration report.
- Why new code was necessary: existing promotion and betrayal modules answer narrower questions; R304 needs one combined preview packet across current Tiny Live, live-qualified, near-miss, broader paper-only, and betrayal/inverse candidates.
- Why this is not duplicating prior work: it does not recompute promotion authority or change ledgers; it reads existing evidence and reports preview-only recommendations with all live/submit/order flags false.
