# R133 Lane Control Cockpit UI

## Phase

R133 Lane Control Cockpit UI

## Branch

`r133-lane-control-cockpit-ui`

## Phase Classification

- Primary classification: EXTENSION OF EXISTING CAPABILITY
- Secondary classification(s): WIRING / INTEGRATION, DIAGNOSTIC / AUDIT, DUPLICATE RISK
- Duplicate risk level: HIGH

## Goal

Create or refactor the operator UI around autonomous lanes instead of manual signal approvals. The cockpit must make lane state, router state, scheduler state, paper execution proof, tiny-live gates, kill-switch status, and R132 boundary review status visible without adding real order buttons or Binance calls.

## Non-Negotiables

- Do not place real orders.
- Do not create executable Binance order payloads.
- Do not call Binance order endpoints.
- Do not send signed requests.
- Do not print secrets.
- Do not mutate env files.
- Do not enable global live execution.
- Do not bypass R106/global gates.
- Do not implement real execution adapter behavior.
- Do not create a live order endpoint.
- Do not install/start systemd services.
- Do not run sudo.
- Do not commit, merge, tag, push, deploy, or restart services.

## Required UI Scope

The cockpit should prioritize:

- global kill switch display
- lane cards
- router state
- autonomy scheduler status
- autonomous paper execution status
- tiny-live gate status
- R130 authorization status
- R131 kill-switch rehearsal status
- R132 boundary review status
- safe command hints for preview/recheck flows

No real order buttons are allowed. No Binance calls are allowed.

## Capability Scan

Inspect before implementation:

- `AGENTS.md`
- `AGENTS.builder.md`
- `AGENTS.index.md`
- `AGENTS.qa.md`
- `AGENTS.security.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `docs/hammer_radar/live_readiness/R122_AUTONOMOUS_LANE_CONTROL.md`
- `docs/hammer_radar/live_readiness/R123_FRESH_SIGNAL_ROUTER.md`
- `docs/hammer_radar/live_readiness/R128_LANE_AUTONOMY_SCHEDULER.md`
- `docs/hammer_radar/live_readiness/R129_AUTONOMOUS_PAPER_LANE_EXECUTOR_INTEGRATION.md`
- `docs/hammer_radar/live_readiness/R130_FIRST_TINY_LIVE_AUTONOMOUS_LANE_AUTHORIZATION.md`
- `docs/hammer_radar/live_readiness/R131_LIVE_LANE_KILL_SWITCH_REHEARSAL.md`
- `docs/hammer_radar/live_readiness/R132_LIVE_ADAPTER_BOUNDARY_FINAL_REVIEW.md`
- existing operator API/UI routes
- `src/app/hammer_radar/operator/inspect.py`
- lane, router, scheduler, paper executor, R126, R130, R131, and R132 modules
- tests under `tests/hammer_radar/`

## Reuse / Extend / Create Decision

Prefer extending existing operator UI/API surfaces. Reuse existing status builders and JSON summaries. Create new UI code only when existing cockpit surfaces are still centered on manual approval instead of lane operations.

## Tests Required

- UI/API status includes lane cards.
- UI/API status includes global kill switch state.
- UI/API status includes router, scheduler, paper execution, R126, R130, R131, and R132 summaries.
- No UI action can place orders.
- No Binance/order payload/network functions are called.
- Safety flags remain false and paper/live separation remains intact.

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile <changed_python_files>
PYTHONPATH=. .venv/bin/python -m pytest -q <targeted_tests>
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```
