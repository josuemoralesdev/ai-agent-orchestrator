# R260 Tiny-Live Fresh Cycle One-Shot Orchestrator

R260 compresses the post-R259 fresh-cycle sequence for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

It orchestrates existing safe gates only:

1. R253 final public read-only mark/precision refresh.
2. R253B local fresh-context stop/TP, executable payload, and signed request regeneration.
3. R254 submit gate preview recording.
4. R255 actual submit gate dry-preview recording.
5. R258 manual submit checkpoint re-check recording.

R260 does not submit, call Binance order/account/private/signed endpoints, place orders, arm live controls, mutate lane controls, mutate risk config, disable kill switches, write env files, expose secrets, or bypass the child gates.

## Command

Preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-one-shot
```

Run and record the one-shot fresh cycle:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-one-shot \
  --run-fresh-cycle-one-shot \
  --record-fresh-cycle-one-shot \
  --confirm-tiny-live-fresh-cycle-one-shot "I CONFIRM TINY LIVE FRESH CYCLE ONE-SHOT ORCHESTRATION ONLY; REFRESH READONLY MARKET, REGENERATE LOCAL SIGNED REQUEST, RECORD PREVIEWS; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL."
```

Wrong confirmation rejects the run and does not call child gates.

## Ledger

R260 appends only:

`logs/hammer_radar_forward/tiny_live_fresh_cycle_one_shot.ndjson`

The child gates append their own ledgers through their existing exact-confirmed builders. R260 records its wrapper ledger only under the R260 exact phrase.

## Safety Outcome

R260 output must keep:

- `submit_allowed=false`
- `submit_attempted=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `binance_account_endpoint_called=false`
- `private_binance_endpoint_called=false`
- `signed_binance_endpoint_called=false`
- `live_controls_armed_by_phase=false`
- `risk_contract_config_written=false`
- `lane_controls_written=false`
- `secrets_shown=false`
- `secret_values_in_output=false`

If all child steps succeed, R260 points next to live-control review / R261 UI arming. It still reports `operator_should_submit_now=false`.
