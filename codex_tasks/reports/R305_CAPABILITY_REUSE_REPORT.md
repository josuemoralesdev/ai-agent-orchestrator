# R305 Capability Reuse Report

## Phase Classification

- Primary classification: EXTENSION OF EXISTING CAPABILITY
- Secondary classification: DIAGNOSTIC / AUDIT
- Duplicate risk level: MEDIUM
- Reason: R305 ranks Strategy Lab variants from existing R304 evidence. It is close to promotion watcher and Strategy Lab preview logic, so it reuses those sources and keeps a separate paper-only lab ranking output.

## Capability Scan

Existing docs checked:

- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R304_PAPER_REFRESH_DURABILITY_AND_STRATEGY_LAB_PREVIEW.md`
- `docs/hammer_radar/PHASE_CAPABILITY_INDEX_R1_R100.md`

Existing modules checked:

- `src/app/hammer_radar/operator/strategy_lab_preview.py`
- `src/app/hammer_radar/operator/strategy_promotion_watcher.py`
- `src/app/hammer_radar/operator/tiny_live_strategy_lane_selection.py`
- `src/app/hammer_radar/operator/paper_refresh_scheduler.py`
- `src/app/hammer_radar/operator/tiny_live_final_authorization_gate.py`
- `src/app/hammer_radar/operator/tiny_live_final_console.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract_validation.py`
- `src/app/hammer_radar/operator/betrayal_*`

Existing tests checked:

- `tests/hammer_radar/test_strategy_lab_preview.py`
- `tests/hammer_radar/test_paper_refresh_scheduler.py`
- `tests/hammer_radar/test_strategy_promotion_watcher.py`
- `tests/hammer_radar/test_tiny_live_final_authorization_gate.py`
- betrayal paper/source/preview tests under `tests/hammer_radar/`

Existing endpoints checked:

- `GET /tiny-live/final-console`
- `GET /paper-refresh/status`
- `POST /paper-refresh/run`
- Existing operator inspect routes for `strategy-lab-preview` and final console views.

Existing CLI commands checked:

- `python -m src.app.hammer_radar.operator.strategy_lab_preview`
- `python -m src.app.hammer_radar.operator.inspect strategy-lab-preview`
- `python -m src.app.hammer_radar.operator.inspect paper-refresh-status`
- `python -m src.app.hammer_radar.operator.inspect tiny-live-final-console`

Existing scheduler tasks checked:

- `paper_refresh_scheduler` task registry and default watch loop.
- R304 degraded task behavior for `eth_paper_outcome`.

Existing logs/ledgers/configs checked:

- `logs/hammer_radar_forward/strategy_lab_preview.ndjson`
- `logs/hammer_radar_forward/strategy_promotion_status.ndjson`
- `logs/hammer_radar_forward/strategy_promotion_events.ndjson`
- `logs/hammer_radar_forward/strategy_performance.ndjson`
- `logs/hammer_radar_forward/outcomes.ndjson`
- `logs/hammer_radar_forward/signals.ndjson`
- `configs/hammer_radar/autonomous_arming_state.json`
- `configs/hammer_radar/tiny_live_risk_contracts.json`

## Reusable Data Sources

- R304 Strategy Lab preview candidates and betrayal preview candidates.
- Strategy performance grouped evidence from `build_live_eligibility_matrix`.
- Promotion watcher candidate buckets and review-only event ledgers.
- Outcomes-derived fill and stop rates already surfaced by R304.
- Final gate and paper refresh health surfaces for operator context only.

## Existing Scoring Logic

R304 already computes:

- `watch_category`
- sample count
- win rate
- average and total PnL
- fill rate
- stop rate
- source chain
- risk-contract compatibility preview
- preview-only recommended action

R305 adds a lab-only `strategy_lab_score` over those existing facts. It does not change promotion watcher thresholds, live eligibility, current arming state, or risk contract validation.

## Duplicate Risks

- Promotion watcher duplication risk: R305 could accidentally become a second promotion surface. Mitigation: output is explicitly lab-only and always keeps `submit_allowed=false` and `final_command_available=false`.
- Strategy preview duplication risk: R305 could recalculate R304 candidates differently. Mitigation: R305 consumes R304 preview output and adds only variant dimensions and evidence status.
- Betrayal promotion duplication risk: betrayal/inverse rows could look live-eligible. Mitigation: betrayal rows are preview-only and include `betrayal_live_permission=false`.

## Chosen Extension Points

- New module: `src/app/hammer_radar/operator/strategy_lab_variant_test_pack.py`
- New inspect route: `strategy-lab-variant-test-pack`
- New operator script: `scripts/hammer_print_r305_strategy_lab_variant_pack.sh`
- New ledger: `logs/hammer_radar_forward/strategy_lab_variant_test_pack.ndjson`

## Reuse / Extend / Create Decision

- Existing capability reused: R304 Strategy Lab preview and existing promotion/performance evidence.
- Existing capability extended: operator inspect command family.
- New capability created: R305 lab-only variant pack and report ledger.
- Why new code was necessary: variant dimensions, direct evidence status, lab score components, near-miss capture priorities, and betrayal capture priority output are distinct from R304 preview and promotion watcher behavior.
- Why this is not duplicating prior work: R305 does not classify live promotion, mutate gates, or rebuild R304 evidence. It ranks variants for paper evidence capture and future review.

## Why This Phase Is Not A Live Expansion

R305 does not:

- enable live execution
- submit live or test orders
- call Binance order, leverage, or margin endpoints
- mutate live flags
- mutate autonomous arming state
- mutate risk contracts
- produce final commands
- change the current Tiny Live first lane

The current first lane remains:

```text
BTCUSDT|44m|long|ladder_close_50_618
```
