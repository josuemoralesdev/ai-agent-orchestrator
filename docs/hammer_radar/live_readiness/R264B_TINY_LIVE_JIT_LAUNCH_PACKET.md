# R264B Tiny-Live JIT Launch Packet

R264B is the just-in-time launch-prep packet for:

`BTCUSDT|8m|short|ladder_close_50_618`

It compresses the final safe preparation path into one exact-confirmed operator
command:

1. refresh the R262B percentage risk-contract fit signed triplet
2. arm R263 final-console controls with explicit experimental-lane acceptance
3. record the R264 actual-submit dry preview
4. validate the exact three-order packet, freshness, risk, controls, and
   idempotency
5. print the final human-run live submit command only when the packet is GO

R264B does not submit, place orders, call Binance order/test-order/account
endpoints, call private/signed Binance endpoints, disable kill switches, change
strategy promotion, mutate paper outcomes, or run the final command.

## Lane Warning

The active lane is the 8m short lane. It remains paper-only /
promotion-mismatched by default and is allowed here only as a manual
experimental tiny-live lane after the exact R263 acceptance phrase. The
promotion-ready lanes remain:

- `BTCUSDT|13m|long|ladder_close_50_618`
- `BTCUSDT|44m|long|ladder_close_50_618`

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-jit-launch-packet
```

Run JIT prep, still no submit:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-jit-launch-packet \
  --run-jit-launch-prep \
  --record-jit-launch-packet \
  --confirm-jit-launch-prep "I CONFIRM TINY LIVE JIT LAUNCH PREP ONLY; REFRESH CONTRACT-FIT TRIPLET, ARM R263 EXPERIMENTAL LANE, RUN R264 DRY PREVIEW; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL." \
  --operator-id local_operator \
  --reason "Final JIT prep for first tiny-live BTCUSDT 8m short experimental lane."
```

Rejected:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-jit-launch-packet \
  --run-jit-launch-prep \
  --record-jit-launch-packet \
  --confirm-jit-launch-prep "wrong"
```

## GO Requirements

The packet is GO only when all are true:

- R262B regeneration succeeded
- risk contract remains valid and no looser than the known 88 / 44 / 10x model
- latest signed triplet is fresh
- R263 controls are armed at runtime
- R263 experimental 8m short lane acceptance is recorded
- R264 dry preview is recorded and pre-submit valid
- idempotency is clean with no prior live submit
- exact three orders are present
- main order is `SELL MARKET 0.006 BTC`
- stop is `BUY STOP_MARKET reduceOnly`
- take-profit is `BUY TAKE_PROFIT_MARKET reduceOnly`

Even on GO, R264B reports `operator_should_submit_now=false`. The operator must
manually review and run the printed R264 command outside Codex.

## Ledger

R264B appends only:

`logs/hammer_radar_forward/tiny_live_jit_launch_packet.ndjson`

Confirmed JIT prep may also append the expected child ledgers:

- `tiny_live_percentage_risk_contract_fit.ndjson`
- `tiny_live_final_console.ndjson`
- `tiny_live_actual_submit_reconciliation.ndjson`

Confirmed R262B may safely update equivalent/stricter percentage fields in
`configs/hammer_radar/tiny_live_risk_contracts.json`.

Confirmed R263 may update only the official lane row in
`configs/hammer_radar/lane_controls.json`.

## API And UI

- `GET /tiny-live/jit-launch-packet`
- `POST /tiny-live/jit-launch-packet/run`

The dashboard includes a Tiny Live JIT Launch Packet card. It shows R262B,
R263, and R264 status, the manual command packet, and a no-submit warning. It
has no auto-submit button.
