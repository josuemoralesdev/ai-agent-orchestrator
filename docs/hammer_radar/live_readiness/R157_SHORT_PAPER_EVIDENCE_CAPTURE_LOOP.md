# R157 Short Paper Evidence Capture Loop

Phase: R157

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Why R157 Follows R156

R156 packaged the `BTCUSDT|8m|short|ladder_close_50_618` strategy family and found promising historical paper outcome evidence:

- mode: paper
- win rate: 54.65 percent
- average PnL: positive
- paper outcome count: 172
- fill rate: 97.18 percent

R156 still blocked any future tiny-live discussion because fresh short candidate evidence was missing. The blocker was `fresh short candidate sample below 10`.

## What R157 Adds

R157 adds a focused bounded capture loop for:

```text
BTCUSDT|8m|short|ladder_close_50_618
```

The loop reads recent local `signals.ndjson` and `multi_symbol_paper_scans.ndjson` rows, normalizes entry mode through the existing read-path bridge where applicable, checks the read-only lane config, and records local paper evidence only when a fresh matching short candidate is present.

## Heartbeat And Bounded Scan

The loop uses bounded recent readers:

- default latest signals: 500
- default latest scans: 1000
- default max iterations: 60
- default sleep seconds: 60
- default iteration timeout: 30 seconds
- default heartbeat cadence: every iteration

Heartbeat records append to:

```text
logs/hammer_radar_forward/short_paper_evidence_capture_heartbeats.ndjson
```

Final capture-loop records append to:

```text
logs/hammer_radar_forward/short_paper_evidence_capture.ndjson
```

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  short-paper-evidence-capture-loop \
  --lane-key "BTCUSDT|8m|short|ladder_close_50_618" \
  --latest-signals 500 \
  --latest-scans 1000
```

Short smoke loop:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  short-paper-evidence-capture-loop \
  --lane-key "BTCUSDT|8m|short|ladder_close_50_618" \
  --latest-signals 500 \
  --latest-scans 1000 \
  --max-iterations 2 \
  --sleep-seconds 1 \
  --iteration-timeout-seconds 30 \
  --heartbeat-every 1 \
  --run-capture-loop \
  --record-capture \
  --confirm-short-paper-capture "I CONFIRM SHORT PAPER EVIDENCE CAPTURE ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."
```

Sixty-minute capture loop:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  short-paper-evidence-capture-loop \
  --lane-key "BTCUSDT|8m|short|ladder_close_50_618" \
  --latest-signals 500 \
  --latest-scans 1000 \
  --max-iterations 60 \
  --sleep-seconds 60 \
  --iteration-timeout-seconds 30 \
  --heartbeat-every 1 \
  --run-capture-loop \
  --record-capture \
  --confirm-short-paper-capture "I CONFIRM SHORT PAPER EVIDENCE CAPTURE ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."
```

## Safety Boundary

R157 does not promote the short lane, set tiny-live, mutate lane config, mutate env, enable live flags, create order payloads, sign requests, call Binance, or place orders.

The target lane remains paper-only. R157 evidence may support a future review packet, but it does not authorize execution.

## Next Possible Phase

R158 should run after short paper evidence capture records exist. It should re-run the short strategy packet and full-spectrum betrayal short review, then decide whether the fresh evidence threshold is met. R158 may build a promotion-readiness packet only. It must not change lane mode or execute live orders.
