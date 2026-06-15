# R262B Tiny-Live Percentage Risk Contract Fit Triplet

R262B converts the official tiny-live lane risk contract to the equivalent
percentage wallet model and regenerates a fresh contract-fit signed triplet:

`BTCUSDT|8m|short|ladder_close_50_618`

The resolved current model stays unchanged:

- isolated risk wallet: `88 USDT`
- position margin: `50%` of wallet, resolved to `44 USDT`
- leverage: `10x`
- max notional: `440 USDT`
- max loss: `4.44 USDT`

The extra `44 USDT` is isolated wallet buffer. It is not position margin.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-percentage-risk-contract-fit
```

Run and record the contract-fit regeneration:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-percentage-risk-contract-fit \
  --run-contract-fit-regeneration \
  --record-contract-fit-regeneration \
  --confirm-contract-fit-regeneration "I CONFIRM TINY LIVE PERCENTAGE RISK CONTRACT FIT REGENERATION ONLY; 88 USDT ISOLATED WALLET, 44 USDT POSITION MARGIN, 10X LEVERAGE, KEEP RISK SAME OR STRICTER; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL."
```

Wrong confirmation rejects without child gate calls:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-percentage-risk-contract-fit \
  --run-contract-fit-regeneration \
  --record-contract-fit-regeneration \
  --confirm-contract-fit-regeneration "wrong"
```

## Mutation Boundary

Preview writes nothing.

Confirmed R262B may update only:

`configs/hammer_radar/tiny_live_risk_contracts.json`

The config update may add percentage-model fields only when resolved risk is the
same or stricter. It must not raise position margin above `44`, max notional
above `440`, max loss above `4.44`, or leverage above `10`.

Confirmed R262B may append its own ledger and child review ledgers:

`logs/hammer_radar_forward/tiny_live_percentage_risk_contract_fit.ndjson`

It must not update:

- `configs/hammer_radar/lane_controls.json`
- env files
- paper outcomes
- strategy performance
- strategy promotion status

## Regeneration

R262B reuses the existing safe chain:

1. R253 public readonly mark/precision refresh.
2. R253B local signed request regeneration.
3. R254 submit gate preview.
4. R255 dry preview.
5. R261 controls review only.

R253B now derives regenerated quantity from the resolved contract and Binance
step size. If `0.007 BTC` would exceed `440 USDT` at the fresh mark, quantity is
rounded down to the largest step-valid amount that fits. The triplet remains
exactly three orders, with reduce-only stop and take-profit exits.

## Safety

R262B always reports:

- `submit_allowed=false`
- `submit_attempted=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `binance_account_endpoint_called=false`
- `private_binance_endpoint_called=false`
- `signed_binance_endpoint_called=false`
- `live_controls_armed_by_phase=false`
- `lane_controls_written=false`
- `secrets_shown=false`
- `secret_values_in_output=false`

If the regenerated dry preview is valid, the next operator step is R263 final
console review and experimental-lane-aware controls arming. R262B itself is not
a submit phase and does not arm controls.

R264B can orchestrate R262B regeneration as the first step in a just-in-time
launch packet, then continue to R263 arming and R264 dry preview. R264B still
does not submit, place orders, call Binance order/private/account endpoints, or
run the final live command.
