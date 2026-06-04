# R192 Lane Matrix After Crow Rescoring

## Purpose

Rerun the paper-only lane x signal-origin matrix after R191 rescored `three_black_crows` with local detector evidence.

## Scope

- Read R191 `keter_rescore_after_three_black_crows.ndjson`.
- Read existing R184 lane matrix inputs and local paper evidence.
- Compare `BTCUSDT|8m|short|ladder_close_50_618 + hammer_wick_reversal` against `BTCUSDT|8m|short|ladder_close_50_618 + three_black_crows`.
- Report whether Three Black Crows is a paper-tracking candidate, needs more paper outcomes, or needs more detector history.
- Recommend next paper-only operator action.

## Safety

R192 must not:

- write config
- mutate env
- call Binance or any network
- create order, protective, transfer, or withdraw payloads
- sign requests
- place orders or test orders
- change lane modes
- set any lane `tiny_live`
- write risk-contract config
- promote signal origins
- promote lanes
- authorize live execution

## Expected Command

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-matrix-after-crow-rescoring
```

## Confirmation

If recording is added, it must require an exact no-config-write, no-order, no-Binance confirmation phrase and append only a new R192 audit ledger.
