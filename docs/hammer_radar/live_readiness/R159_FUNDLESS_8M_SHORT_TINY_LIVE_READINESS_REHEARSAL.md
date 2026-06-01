# R159 Fundless 8m Short Tiny-Live Readiness Rehearsal

Phase: R159

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Why R159 Follows R158

R158 rechecked the R157 fresh paper capture state for:

```text
BTCUSDT|8m|short|ladder_close_50_618
```

R158 found the lane remains paper and the fresh short capture count is still below the 10-capture threshold. R159 builds the fundless readiness shell while R157 continues collecting evidence, so the operator can see what is ready, what is blocked, and what future conditions must be satisfied before any short tiny-live discussion.

R159 is progress because it prepares the audit and arming checklist without waiting idly for account funding or fresh evidence. It does not promote the lane.

## What R159 Adds

R159 adds:

- `src/app/hammer_radar/operator/fundless_short_tiny_live_readiness_rehearsal.py`
- CLI mode `fundless-short-tiny-live-readiness-rehearsal`
- append-only ledger `logs/hammer_radar_forward/fundless_short_tiny_live_readiness_rehearsals.ndjson`

The rehearsal composes:

- R158 short evidence recheck output
- R156 short strategy packet evidence
- R157 short paper capture records
- read-only `configs/hammer_radar/lane_controls.json`
- read-only local risk-contract config presence

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fundless-short-tiny-live-readiness-rehearsal \
  --latest-captures 200 \
  --latest-outcomes 10000 \
  --latest-signals 3000
```

Record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fundless-short-tiny-live-readiness-rehearsal \
  --latest-captures 200 \
  --latest-outcomes 10000 \
  --latest-signals 3000 \
  --record-rehearsal \
  --confirm-fundless-short-rehearsal "I CONFIRM FUNDLESS SHORT READINESS REHEARSAL RECORDING ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."
```

## Fundless Readiness Gates

The target lane remains:

```text
BTCUSDT|8m|short|ladder_close_50_618 = paper
```

Evidence gate:
- requires at least 10 fresh short captures
- reuses R158 promotion-readiness evidence
- blocks while R157 fresh captures remain below threshold

Funding gate:
- reports `UNKNOWN_NOT_CHECKED` by default
- does not call Binance
- does not require account network access
- blocks future live discussion until funding is verified by a later safe process

Short strategy gate:
- preserves the short golden-pocket role as resistance/retrace
- requires short-specific stop/TP review before any future live discussion
- reuses R156/R158 evidence and does not create new strategy authority

Risk contract preview:
- reads only local config
- reports whether a target-lane risk contract exists
- keeps suggested notional null
- remains non-executable preview only

## Non-Executable Dry-Run Intent

R159 emits a dry-run intent preview with:

- `would_build_order_payload=false`
- `would_submit_order=false`
- `would_call_binance=false`
- `executable=false`
- `notional_usdt=null`

This is not a Binance payload, not a protective payload, not a signed request, and not execution authority.

## Safety Boundary

R159 does not:

- place orders
- create executable Binance order payloads
- create protective order payloads
- call Binance order or test-order endpoints
- sign requests
- mutate `.env`
- mutate `lane_controls.json`
- set any short lane to `tiny_live`
- change existing `tiny_live` lane modes
- change global live flags
- disable the kill switch
- start or restart services

## Next Possible R160

R160 should build a more detailed non-executable dry-run packet and operator arming checklist. It should define funding verification steps and future lane-promotion review steps while preserving:

- no lane mode change
- no live execution
- no Binance order calls
- no executable payloads
