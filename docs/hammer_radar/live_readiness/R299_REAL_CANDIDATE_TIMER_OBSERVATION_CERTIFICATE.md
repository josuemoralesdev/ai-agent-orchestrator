# R299 Real-Candidate Timer Observation Certificate

R299 certifies that the existing dry-run timer and scheduler can observe the R298 real-candidate dry-run trigger bridge state over recent ticks.

It reuses the existing R298 bridge, R292/R293 timer health, R288 scheduler ledger, R287 trigger loop status, R294/R295 dry-run wait surfaces, and the final console. It does not create a parallel scheduler, timer, candidate watcher, bridge, approval path, or order path.

## Outcomes

- `REAL_CANDIDATE_TIMER_OBSERVATION_READY_TO_WAIT_CERTIFIED`: timer health is active, recent timer ticks exist, scheduler ticks exist, and R298 reports `REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT`. This is the expected state when no real candidate exists.
- `REAL_CANDIDATE_TIMER_OBSERVATION_TRIGGER_CERTIFIED`: timer and scheduler observation are present, and R298 reports `REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED` from a real matching fresh candidate. R299 copies the simulated dry-run lifecycle summary from R298 only.
- `REAL_CANDIDATE_TIMER_OBSERVATION_BLOCKED`: R298 is blocked, timer recent tick evidence is missing, scheduler recent tick evidence is missing, or the requested lane is invalid.

## Real Candidate Only

R299 does not inject candidates and does not expose simulation arguments in the public CLI or API. Runtime status reads R298, which reads the real fresh-trigger-watch surface.

The packet asserts:

- `test_only=false`
- `fake_candidate_used=false`
- `real_candidate_source="fresh_trigger_watch_via_r298_bridge"`
- `exact_lane_only=true`
- `no_cross_lane_borrowing=true`

## Safety

R299 is dry-run observation and certification only:

- no live execution enable
- no final submit command
- no submit allowed
- no executable payload
- no order payload
- no live order
- no Binance order endpoint
- no Binance test order endpoint
- no leverage or margin mutation endpoint
- no env, live config, risk contract, lane control, or installed timer mutation
- no secrets shown
- no per-signal operator approval requirement

Alerts and panels are visibility/audit only. Operator arms, disarms, tunes risk, and kills the system; the machine may only auto-trigger under already-open gates in future phases.

## Interfaces

CLI:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-real-candidate-timer-observation-certificate \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R299 real-candidate timer observation certificate; no fake candidate; no submit; no order." \
  --record-real-candidate-timer-observation-certificate
```

API:

```text
GET /tiny-live/real-candidate-timer-observation-certificate/status
GET /tiny-live/real-candidate-timer-observation-certificate/status?lane_key=BTCUSDT|44m|long|ladder_close_50_618
```

The API is read-only and never records the R299 ledger.

Final console:

```text
real_candidate_timer_observation_certificate_panel
```

Print-only helper:

```bash
bash scripts/hammer_print_r299_real_candidate_timer_observation_certificate_plan.sh
```

## Expected Next Phase

The expected next phase should continue observing real candidates under timer control and define any additional operator visibility needed before a protected live path. It must still keep final submit, live execution, executable order payloads, Binance order/test-order endpoints, and live config mutation unavailable unless a future explicitly approved live phase defines a separate protected gate.
