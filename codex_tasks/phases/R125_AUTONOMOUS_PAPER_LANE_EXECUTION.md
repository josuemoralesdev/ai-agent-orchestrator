# R125 Autonomous Paper Lane Execution

## Phase

`R125`

## Branch

`r125-autonomous-paper-lane-execution`

## Phase Classification

- Primary classification: EXTENSION OF EXISTING CAPABILITY
- Secondary classification(s): WIRING / INTEGRATION, DIAGNOSTIC / AUDIT
- Duplicate risk level: MEDIUM

## Reason

R122 created lane-control intent, R123 routes fresh candidates into lanes, and R124 lets the operator safely change lane modes. R125 should execute only paper lane records for fresh routed candidates so autonomous lane behavior can be measured without touching live execution.

## Main Objective

Implement autonomous paper lane execution records from R123 routed fresh signals while respecting R122/R124 lane mode, freshness, max daily trade limits, cooldowns, and existing paper/live separation.

## Capability Scan

Before implementation inspect:

- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `codex_tasks/phases/R124_LANE_COMMAND_INTERFACE.md`
- `docs/hammer_radar/live_readiness/R122_AUTONOMOUS_LANE_CONTROL.md`
- `docs/hammer_radar/live_readiness/R123_FRESH_SIGNAL_ROUTER.md`
- `docs/hammer_radar/live_readiness/R124_LANE_COMMAND_INTERFACE.md`
- `src/app/hammer_radar/operator/lane_control.py`
- `src/app/hammer_radar/operator/fresh_signal_router.py`
- `src/app/hammer_radar/operator/lane_command_interface.py`
- existing paper execution modules and ledgers
- `configs/hammer_radar/lane_controls.json`
- tests under `tests/hammer_radar/`
- existing `inspect.py` CLI modes
- approval/operator API surfaces only if a read-only/status endpoint is clearly low risk

## Reuse / Extend / Create Decision

- Existing capability reused: R122 lane config/evaluation, R123 fresh-signal routing, existing paper execution record patterns.
- Existing capability extended: operator inspect/status surfaces for paper lane execution.
- New capability created: a paper-only lane execution adapter and append-only paper lane ledger if no existing ledger cleanly fits.
- Why new code is necessary: R123 routes candidates but intentionally does not create paper execution records.
- Why this does not duplicate prior work: R125 must wire routed candidates into existing paper-only execution patterns rather than creating another live or approval path.

## Required Behavior

- Route fresh signals from R123.
- Create paper execution records only.
- Respect lane modes:
  - `disabled`: no paper execution.
  - `paper`: eligible for paper execution.
  - `armed_dry_run`: diagnostic/dry-run only unless the phase explicitly defines paper behavior.
  - `tiny_live`: no real order; may create paper mirror records only if explicitly scoped and safe.
- Respect `max_daily_trades`.
- Respect `cooldown_after_loss_minutes`.
- Respect `freshness_seconds`.
- Preserve `max_daily_loss_pct` as a blocking risk limit.
- Write append-only audit records.
- Return compact status.

## Safety Constraints

- Do not place real orders.
- Do not create Binance order payloads.
- Do not call Binance order endpoints.
- Do not call account or balance endpoints.
- Do not mutate env files.
- Do not enable global live execution.
- Do not bypass R106/global gates.
- Do not create a live order endpoint.
- Do not weaken lane risk limits.
- Do not treat paper execution as live approval.
- Do not expose secrets.

## Expected CLI

Add an inspect mode such as:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  autonomous-paper-lane-execution
```

Default behavior should be preview/dry-run unless the phase defines an explicit paper-only write flag and confirmation phrase.

## Required Tests

Test:

- fresh R123 routed signal creates paper record only when lane mode permits
- disabled lane is blocked
- stale signal is blocked
- `max_daily_trades` is enforced
- cooldown after loss is enforced
- `max_daily_loss_pct` is preserved and enforced
- no real order is placed
- no Binance order payload is created
- no Binance order endpoint is called
- no env files are mutated
- audit ledger records paper-only action
- CLI mode returns compact status
- R123 router remains compatible

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile src/app/hammer_radar/operator/inspect.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_fresh_signal_router.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

Add focused R125 tests and run them before broader validation.

## Do Not

- Do not commit.
- Do not merge.
- Do not tag.
- Do not push.
- Do not deploy.
- Do not run `sudo`.
- Do not restart services.
- Do not place live orders under any circumstance.
