# Phase R152 Candidate Opportunity Expansion Audit

## Phase

`R152`

## Branch

`r152-candidate-opportunity-expansion-audit`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## Reason

R151 may show that the R150 watcher was healthy and source feeds were live, but the current BTCUSDT 13m/44m long target lanes produced no fresh paper-proof opportunity during the watch window. R152 should compare opportunity distribution across timeframes and directions before any operator considers future paper-only expansion.

## Assigned Agents

- builder: implement scoped audit/report surfaces only
- index: map existing source, lane, paper, and watcher capabilities before implementation
- qa: validate no writes by default and no live/order side effects
- security: enforce no live execution, no Binance/private calls, and no lane widening

## Main Objective

Compare long/short and timeframe opportunity distribution across 4m/8m/13m/44m/88m paper/source candidates, identify whether current target lanes are too narrow, and recommend paper-only expansion candidates without changing live lanes.

## Capability Scan

Inspect before implementation:

- `docs/hammer_radar/live_readiness/R151_CANDIDATE_SOURCE_FRESHNESS_AND_PROOF_STARVATION_AUDIT.md`
- `src/app/hammer_radar/operator/candidate_source_freshness_audit.py`
- `src/app/hammer_radar/operator/signal_to_watcher_eligibility_trace.py`
- `src/app/hammer_radar/operator/fresh_signal_router.py`
- `src/app/hammer_radar/operator/entry_mode_derivation_bridge.py`
- `src/app/hammer_radar/operator/lane_control.py`
- `src/app/hammer_radar/operator/autonomous_paper_lane_executor_integration.py`
- `logs/hammer_radar_forward/signals.ndjson`
- `logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson`
- `logs/hammer_radar_forward/paper_refresh_runs.ndjson`
- `configs/hammer_radar/lane_controls.json`
- related tests under `tests/hammer_radar/`

## Required Behavior

- Report opportunity counts by symbol, timeframe, direction, entry mode, freshness, and paper eligibility.
- Compare current live target lanes against nearby paper-only lanes: 4m, 8m, 13m, 44m, and 88m; long and short.
- Recommend paper-only expansion candidates when data supports them.
- Do not change lane config.
- Do not widen live lanes.
- Do not add live short lanes.
- Do not create proof.
- Do not start watchers or services.
- Do not call Binance or any private/account/order endpoint.

## Output

Return JSON with:

- status
- generated_at
- source_window
- current_target_lane_summary
- opportunity_distribution
- paper_only_expansion_candidates
- blockers
- recommended_next_operator_move
- recommended_next_engineering_move
- safe_commands
- do_not_run_yet
- safety
- source_surfaces_used

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/candidate_opportunity_expansion_audit.py \
  src/app/hammer_radar/operator/inspect.py

PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_candidate_opportunity_expansion_audit.py
```

## Safety Constraints

- No live execution.
- No real orders.
- No executable Binance order payloads.
- No protective payloads.
- No Binance order/test/protective/private/account calls.
- No signed requests.
- No env mutation.
- No lane config mutation.
- No global live flag mutation.
- No kill-switch disable.
- No freshness bypass.
- No fake paper proof.
- No live lane widening without future explicit operator approval.

## Final Report

Report branch, classification, capability scan, reuse/extend/create decision, duplicate risk report, files changed, validations, smoke checks, opportunity recommendation, and safety result.
