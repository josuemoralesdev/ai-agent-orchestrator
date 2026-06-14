# R262A Tiny-Live Risk Contract Fix And Controls Recheck

R262A diagnoses the R261 `risk_contract_invalid` blocker for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

It reads the local risk contract, the R261 controls review path, the latest R260
fresh-cycle record, the latest R255 dry preview, and lane controls. It does not
submit, sign, regenerate signed requests, call Binance/network, place orders,
read secrets, or write env files.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-fix
```

Record diagnostic only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-fix \
  --record-risk-contract-diagnostic \
  --confirm-risk-contract-diagnostic "I CONFIRM TINY LIVE RISK CONTRACT DIAGNOSTIC RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

Apply the validator/config fix only when the plan is safe:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-fix \
  --apply-risk-contract-fix \
  --confirm-risk-contract-fix "I CONFIRM TINY LIVE RISK CONTRACT FIX FOR BTCUSDT 8M SHORT ONLY; KEEP RISK LIMITS SAME OR STRICTER; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

Apply the safe fix and arm controls only if the risk contract recheck is valid:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-fix \
  --apply-risk-contract-fix \
  --confirm-risk-contract-fix "I CONFIRM TINY LIVE RISK CONTRACT FIX FOR BTCUSDT 8M SHORT ONLY; KEEP RISK LIMITS SAME OR STRICTER; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  --arm-controls-after-fix \
  --confirm-arm-tiny-live-controls "I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  --operator-id local_operator \
  --reason "R262A risk contract valid; R260 fresh cycle valid; preparing for R262 final submit console."
```

## Diagnostic Result

R262A fixes the validator wiring that dropped the local `entry_reference_price`
from the R253B/R254/R255 path. The submit-gate validator now requires local
reference context instead of falling back to a stale hard-coded price, and R261
can recheck legacy R255 dry previews using the matching R260 fresh mark.

The fix does not increase margin budget above `44 USDT`, leverage above `10x`,
max notional above `440 USDT`, or max loss above `4.44 USDT`.

If the current dry-preview triplet still exceeds those limits, R262A reports
`root_cause=unsafe_limits`, keeps controls arming blocked, and points to a later
authorized fresh-cycle/regeneration phase. R262A itself must not regenerate,
sign, submit, or call Binance.

## API

- `GET /tiny-live/risk-contract/review`
- `POST /tiny-live/risk-contract/fix/record`
- `POST /tiny-live/risk-contract/fix/apply`

The endpoints return JSON and do not submit, sign, call Binance, or place
orders. The Tiny Live Controls UI displays the R262A root cause and fix status;
it still has no submit button.

## Ledger

Confirmed diagnostic/fix attempts append only:

`logs/hammer_radar_forward/tiny_live_risk_contract_fix.ndjson`

Controls arming, when allowed by a valid recheck and exact phrase, still reuses
the R261 lane-control writer and can update only:

`configs/hammer_radar/lane_controls.json`

## R262 Handoff

R262 final submit console must require R262A risk contract recheck valid,
R261/R262A controls armed, R260 fresh cycle valid, the latest signed triplet
shown with freshness, and no auto-submit by default.
