# R251C Tiny-Live Signed Request Write With Credentials Drill

## Purpose

R251C should rerun the existing R251 signed request write gate after the operator has set `BINANCE_API_KEY` and `BINANCE_API_SECRET` in the process environment outside Git.

## Scope

- Assume signing credentials are present in the process environment.
- Use the existing R251 signed request write gate exact confirmation.
- Write the local signed request artifact only.
- Do not call Binance.
- Do not submit.
- Do not place orders.
- Do not mutate `.env`, configs, lane controls, scheduler config, or live flags.
- Do not expose or persist raw credential values.

## Primary Command

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signed-request-write-gate \
  --write-signed-request \
  --confirm-tiny-live-signed-request-write "I CONFIRM TINY LIVE SIGNED REQUEST WRITE GATE ONLY; WRITE LOCAL SIGNED REQUEST ARTIFACT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

## Required Safety Result

- `submit_allowed=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `network_allowed=false`
- `secrets_shown=false`
- `secrets_persisted=false`
