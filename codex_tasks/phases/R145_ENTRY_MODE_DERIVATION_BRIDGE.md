# R145 Entry Mode Derivation Bridge

## Phase

`R145`

## Branch

`r145-entry-mode-derivation-bridge`

## Phase Classification

- Primary classification: WIRING / INTEGRATION
- Secondary classification(s): EXTENSION OF EXISTING CAPABILITY, DIAGNOSTIC / AUDIT
- Duplicate risk level: HIGH

## Reason

R144 traces why visible BTCUSDT 13m/44m signals do not become R142 watcher-eligible paper proof candidates. The likely confirmed gap is that visible signals match watched symbol/timeframe/direction, but lack `entry_mode=ladder_close_50_618`, so they cannot exactly match:

- `BTCUSDT|13m|long|ladder_close_50_618`
- `BTCUSDT|44m|long|ladder_close_50_618`

## Main Objective

Derive or attach `entry_mode` for eligible BTCUSDT 13m/44m signals and normalize paper scan candidates into lane-key-addressable records so the existing fresh router can emit watched lane candidates when timeframe/direction/entry logic match.

## Capability Scan

Inspect before implementation:

- `src/app/hammer_radar/operator/signal_to_watcher_eligibility_trace.py`
- `src/app/hammer_radar/operator/fresh_signal_router.py`
- `src/app/hammer_radar/operator/autonomous_paper_lane_executor_integration.py`
- `src/app/hammer_radar/operator/lane_autonomy_control_loop.py`
- `src/app/hammer_radar/operator/lane_autonomy_scheduler.py`
- `src/app/hammer_radar/operator/multi_symbol_scanner.py`
- `src/app/hammer_radar/operator/betrayal_paper_signal_detector.py`
- `tests/hammer_radar/test_signal_to_watcher_eligibility_trace.py`
- `tests/hammer_radar/test_fresh_signal_router.py`
- `tests/hammer_radar/test_autonomous_paper_lane_executor_integration.py`
- `docs/hammer_radar/live_readiness/R144_SIGNAL_TO_WATCHER_ELIGIBILITY_TRACE.md`

## Required Constraints

- No live execution.
- No Binance calls.
- No order payloads.
- No protective payloads.
- No signed requests.
- No env mutation.
- No global flag mutation.
- No lane config mutation unless a future R145 task explicitly scopes it and preserves R124 as the mutation interface.
- Preserve R106/global gates and R142 watcher safety.

## Expected Work

- Reuse R144 trace findings.
- Add a small derivation/normalization bridge instead of changing R142 watcher rules.
- Preserve exact lane-key matching after `entry_mode` is derived.
- Add tests proving missing entry mode can be normalized into `ladder_close_50_618` only when the candidate satisfies the approved BTCUSDT lane logic.
- Keep paper/live separation intact.

## Validation

Run focused tests first:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_signal_to_watcher_eligibility_trace.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_fresh_signal_router.py tests/hammer_radar/test_autonomous_paper_lane_executor_integration.py
```

Then run broader Hammer Radar tests if runtime scope warrants:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

## Final Report

Report the R144 aggregate gap counts used, the derivation rule added, files changed, tests run, and safety result. Do not claim live readiness or execution authority.
