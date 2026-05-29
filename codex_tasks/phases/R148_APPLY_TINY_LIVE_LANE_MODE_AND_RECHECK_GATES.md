# R148 Apply Tiny-Live Lane Mode And Recheck Gates

## Phase

`R148`

## Branch

`r148-apply-tiny-live-lane-mode-and-recheck-gates`

## Phase Classification

- Primary classification: WIRING / INTEGRATION
- Secondary classification(s): DIAGNOSTIC / AUDIT
- Duplicate risk level: HIGH

## Reason

R147 made the `lane-control-command` tiny-live mode intent path fast and bounded. R148 should use that fixed path to apply operator lane intent for the BTCUSDT 13m and 44m long lanes, then recheck the existing gate surfaces without creating execution authority.

## Assigned Agents

- builder: apply only the scoped lane mode intent through the existing R124/R147 command path
- index: verify the phase remains linked to R122/R124/R126/R143-R147 surfaces
- qa: run focused status and gate rechecks
- security: enforce no Binance, no live execution, no env/global mutation, and kill-switch discipline

## Main Objective

Apply `tiny_live` lane mode intent for:

- `BTCUSDT|13m|long|ladder_close_50_618`
- `BTCUSDT|44m|long|ladder_close_50_618`

Then verify lane-control status, first tiny-live lane execution gates, and post-bridge watcher proof capture readiness.

## Capability Scan

Inspect:

- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R147_FAST_LANE_TINY_LIVE_MODE_INTENT_PATH.md`
- `docs/hammer_radar/live_readiness/R124_LANE_COMMAND_INTERFACE.md`
- `docs/hammer_radar/live_readiness/R126_FIRST_TINY_LIVE_LANE_EXECUTION_GATE.md`
- `docs/hammer_radar/live_readiness/R146_POST_BRIDGE_WATCHER_PROOF_CAPTURE_RECHECK.md`
- `src/app/hammer_radar/operator/lane_command_interface.py`
- `src/app/hammer_radar/operator/lane_control.py`
- `src/app/hammer_radar/operator/first_tiny_live_lane_execution_gate.py`
- `src/app/hammer_radar/operator/post_bridge_watcher_proof_capture_recheck.py`
- `configs/hammer_radar/lane_controls.json`
- related tests under `tests/hammer_radar/`

## Required Commands

Preview both lane changes first:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-command \
  --action set-mode \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --mode tiny_live \
  --request-tiny-live
```

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-command \
  --action set-mode \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --mode tiny_live \
  --request-tiny-live
```

Apply only after confirming the preview shows the R147 fast global gate sentinel and safety false flags:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-command \
  --action set-mode \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --mode tiny_live \
  --request-tiny-live \
  --apply \
  --confirm-lane-change "I CONFIRM LANE CONFIG CHANGE ONLY; NO ORDER; NO ENV CHANGE."
```

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-command \
  --action set-mode \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --mode tiny_live \
  --request-tiny-live \
  --apply \
  --confirm-lane-change "I CONFIRM LANE CONFIG CHANGE ONLY; NO ORDER; NO ENV CHANGE."
```

Recheck:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-status
```

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  first-tiny-live-lane-execution-gate \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618"
```

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  first-tiny-live-lane-execution-gate \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618"
```

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  post-bridge-watcher-proof-capture-recheck \
  --trace-all-unlocked-lanes
```

## Safety Constraints

- No Binance calls.
- No live execution.
- No order payloads.
- No protective payloads.
- No signed requests.
- No env mutation.
- No global live flag mutation.
- Do not disable the kill switch.
- Do not bypass R106/global gates.
- Do not create fake paper proof.

## Final Report Format

Report:

- Branch:
- Phase Classification:
- Capability scan summary:
- Files changed:
- Commands run:
- Lane-control status after apply:
- Tiny-live gate results:
- Post-bridge watcher recheck result:
- Safety result:
- Blockers, if any:
