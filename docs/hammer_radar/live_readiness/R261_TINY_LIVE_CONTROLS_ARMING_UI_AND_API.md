# R261 Tiny-Live Controls Arming UI And API

R261 adds the local operator review surface for the official tiny-live lane:

`BTCUSDT|8m|short|ladder_close_50_618`

It consumes the latest R260 one-shot fresh-cycle record, latest R255 dry preview,
`configs/hammer_radar/tiny_live_risk_contracts.json`, and
`configs/hammer_radar/lane_controls.json`.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-controls-arming
```

Record controls review only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-controls-arming \
  --record-controls-review \
  --confirm-tiny-live-controls-review "I CONFIRM TINY LIVE CONTROLS REVIEW RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

Arm lane controls only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-controls-arming \
  --arm-tiny-live-controls \
  --confirm-arm-tiny-live-controls "I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  --operator-id local_operator \
  --reason "R260 fresh cycle valid; preparing for R262 final submit console."
```

## API

- `GET /tiny-live/controls/review`
- `POST /tiny-live/controls/review/record`
- `POST /tiny-live/controls/arm`

The endpoints return JSON and do not submit, sign, call Binance, or place
orders.

## Mutation Boundary

Preview mode writes nothing. Review recording appends only:

`logs/hammer_radar_forward/tiny_live_controls_arming.ndjson`

Arming can additionally update only:

`configs/hammer_radar/lane_controls.json`

The arming write changes only the official lane row to `mode: tiny_live` and
adds R261 audit fields to that row. It preserves unrelated lanes and unrelated
config keys. It does not update the risk contract, env files, paper outcomes,
strategy performance, promotion status, schedulers, or signed request ledgers.

## Safety

R261 always reports `submit_allowed=false`, `order_placed=false`,
`real_order_placed=false`, `execution_attempted=false`,
`binance_order_endpoint_called=false`, `network_allowed=false`, and
`secrets_shown=false`.

If the risk contract is invalid, arming is blocked and the UI/API/CLI surface
keeps the next required step at `FIX_RISK_CONTRACT`.

R262A adds the follow-up diagnostic/fix surface for this blocker. R261 keeps
using local R255/R260 dry-preview evidence for validation and does not treat
controls arming as submit permission.

## R262 Handoff

After controls are armed and blockers are clear, the next engineering step is
R262 final submit console. R262 must consume the R262A risk-contract recheck and
the R261/R262A arming result, show the final signed triplet and freshness age,
show all blockers, and present the exact manual submit command without
auto-submit by default.
