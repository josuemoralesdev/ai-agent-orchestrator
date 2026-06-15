You are in repo:
/home/josue/workspace/kernel/ai-agent-orchestrator-main

Current branch:
r263-tiny-live-final-console-lane-intelligence-controls-arming

Task:
Fix R263 so the full Hammer Radar suite passes.

Problem:
The full test suite failed because configs/hammer_radar/lane_controls.json was mutated so BTCUSDT|8m|short|ladder_close_50_618 became tiny_live before full tests.

This broke legacy expectations:
- test_lane_control.py expects BTCUSDT 8m short ladder_close_50_618 to be paper by default.
- R256/R257/R258/R259 fixtures expect blocker official_lane_not_tiny_live.
- Live authorization preview/write gate tests expect default lane controls not armed.

Non-negotiable fix:
- The repository baseline configs/hammer_radar/lane_controls.json must remain with BTCUSDT|8m|short|ladder_close_50_618 as paper.
- R263 preview must not mutate lane_controls.json.
- R263 review record must not mutate lane_controls.json.
- R263 wrong arming phrase must not mutate lane_controls.json.
- R263 exact arming behavior may mutate lane_controls.json only when the explicit arming command is run manually.
- Tests must not leave real configs mutated.
- Focused R263 tests that test arming must use temp config path or monkeypatch the lane controls path.
- Full test suite must pass after the branch is left in a clean safe baseline state.

Required steps:
1. Inspect tiny_live_final_console.py, tiny_live_controls_arming.py, approval_api.py, inspect.py, and test_tiny_live_final_console.py.
2. Ensure no import-time or preview-time logic writes lane_controls.json.
3. Ensure R263 arming path supports test-injected temp config path or monkeypatches the config path.
4. Ensure tests restore or isolate lane_controls mutations.
5. Restore configs/hammer_radar/lane_controls.json baseline so 8m short remains paper.
6. Do not remove the R263 arming capability, just isolate it correctly.
7. Do not weaken the exact arming phrase requirement.
8. Do not submit.
9. Do not call Binance.
10. Do not sign.
11. Do not place orders.
12. Do not touch AGENTS.md.

Validation:
Run:
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/tiny_live_final_console.py \
  src/app/hammer_radar/operator/tiny_live_controls_arming.py \
  src/app/hammer_radar/operator/approval_api.py \
  src/app/hammer_radar/operator/inspect.py

Run:
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_tiny_live_final_console.py

Run:
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_tiny_live_percentage_risk_contract_fit_regeneration.py \
  tests/hammer_radar/test_tiny_live_controls_arming.py \
  tests/hammer_radar/test_tiny_live_risk_contract_fix.py \
  tests/hammer_radar/test_tiny_live_actual_submit_gate.py \
  tests/hammer_radar/test_lane_control.py \
  tests/hammer_radar/test_tiny_live_operator_real_submit_runbook.py \
  tests/hammer_radar/test_tiny_live_final_pre_submit_arming_drill.py \
  tests/hammer_radar/test_tiny_live_fresh_cycle_checkpoint.py \
  tests/hammer_radar/test_tiny_live_manual_submit_checkpoint.py

Run full:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar

Final report:
- Explain root cause.
- Confirm lane_controls baseline restored.
- Confirm focused/related/full tests pass.
- Confirm no submit/order/Binance/signing.
- Confirm configs/hammer_radar/lane_controls.json is not mutated unless deliberately armed by command.
- Do not commit.
