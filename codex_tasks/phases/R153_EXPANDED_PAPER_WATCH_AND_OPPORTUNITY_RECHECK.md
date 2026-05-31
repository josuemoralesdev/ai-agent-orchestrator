# R153 Expanded Paper Watch And Opportunity Recheck

## Phase

`R153`

## Branch

`r153-expanded-paper-watch-and-opportunity-recheck`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## Reason

R152 expands BTCUSDT 4m/8m/13m/44m long and short visibility for paper-only opportunity collection. R153 should use that expanded paper scope to collect bounded watcher proof and distribution evidence before any future live candidate-family decision.

## Assigned Agents

- builder: implement only the requested recheck/watch support
- index: map existing watcher, audit, lane-control, and paper-proof surfaces
- qa: validate bounded watch/audit behavior and safety flags
- security: confirm no live execution, Binance calls, payloads, env mutation, or gate bypass

## Main Objective

Run or prepare a bounded expanded paper-only watcher/audit over the R152 paper scope, then report candidate distribution across long/short and 4m/8m/13m/44m so the operator can identify the best next live candidate family in a later phase.

## Capability Scan

Inspect at minimum:

- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R152_AGGRESSIVE_PAPER_ONLY_OPPORTUNITY_EXPANSION.md`
- `configs/hammer_radar/lane_controls.json`
- `src/app/hammer_radar/operator/paper_opportunity_expansion.py`
- `src/app/hammer_radar/operator/fresh_candidate_paper_proof_capture_loop.py`
- `src/app/hammer_radar/operator/candidate_source_freshness_audit.py`
- `src/app/hammer_radar/operator/fresh_signal_router.py`
- `src/app/hammer_radar/operator/entry_mode_derivation_bridge.py`
- `src/app/hammer_radar/operator/lane_control.py`
- `tests/hammer_radar/test_paper_opportunity_expansion.py`
- related watcher/audit tests

## Reuse / Extend / Create Decision

- Existing capability reused: R142/R150 bounded watcher, R151 freshness audit, R152 expansion preview/distribution, R122 lane controls, R123 router.
- Existing capability extended: only if expanded paper scope is not already visible in watcher/audit output.
- New capability created: only a small adapter/report if existing surfaces cannot compose the expanded paper scope cleanly.
- Why new code is necessary: to produce a focused post-expansion recheck, not to duplicate watcher or lane-control logic.
- Why this does not duplicate prior work: R153 consumes R152 scope and R150/R151 mechanics instead of creating a new lane config, strategy scorer, or execution path.

## Duplicate Risk Report

- Similar existing modules: R142/R150 watcher, R151 audit, R152 expansion.
- Similar existing endpoints: none expected unless operator API surfaces are explicitly requested.
- Similar existing CLI commands: `fresh-candidate-paper-proof-capture-loop`, `candidate-source-freshness-audit`, `paper-opportunity-expansion`.
- Similar scheduler tasks: lane autonomy scheduler surfaces must remain non-executing.
- Similar docs: R150, R151, R152 live-readiness docs.
- Risk: HIGH because watcher, audit, router, lane-control, and paper-proof surfaces overlap.
- Mitigation: compose existing commands and reports; do not create a competing watcher, lane config, or execution pathway.

## Files Expected

- Optional doc/report for R153 under `docs/hammer_radar/live_readiness/`
- Optional narrow operator adapter if existing commands cannot produce the required expanded distribution
- Tests close to any changed behavior
- Update `docs/hammer_radar/live_readiness/PHASE_INDEX.md`

## Tests Required

- Expanded paper watch scope includes 4m/8m/13m/44m long/short where configured.
- Existing 13m/44m long tiny-live lanes remain unchanged.
- No short lane is tiny-live.
- Watch/audit output reports distribution by timeframe and direction.
- No live execution, Binance calls, payloads, signed requests, env mutation, or global live flag mutation.

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile <changed_python_files>
PYTHONPATH=. .venv/bin/python -m pytest -q <focused_tests>
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

## Safety Constraints

- No live execution.
- No new tiny-live modes.
- No short live authorization.
- No Binance order/test/protective/private calls.
- No executable or signed payloads.
- No env mutation.
- No global live flag mutation.
- No kill-switch disable.
- No fake paper proof.

## Do Not

- Do not run confirmed real-config apply unless explicitly instructed.
- Do not start or restart services.
- Do not run `sudo`.
- Do not commit, merge, tag, push, deploy, or restart production services.

## Final Report Format

Report:

- Branch:
- Phase Classification:
- Capability scan summary:
- Reuse / Extend / Create decision:
- Duplicate risk report:
- Files created:
- Files modified:
- Tests or checks run:
- Smoke checks run, if any:
- Runtime behavior changed:
- Safety result:
- Blockers, if any:
- Exact manual commands needed, if any:
