# R255 Tiny-Live Actual Submit Gate

R255 implements the actual-submit gate machinery for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

This phase does not submit from Codex. The default CLI path is preview-only,
network-disabled, and order-disabled. A dry preview ledger record may be
appended only with the exact dry-preview confirmation phrase.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-gate
```

Record dry preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-gate \
  --dry-run-actual-submit-gate \
  --record-actual-submit-gate-preview \
  --confirm-tiny-live-actual-submit-gate-preview "I CONFIRM TINY LIVE ACTUAL SUBMIT GATE DRY PREVIEW ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

Rejected real-submit proof:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-gate \
  --execute-actual-submit \
  --confirm-tiny-live-actual-submit "wrong"
```

## Gate Checks

- Latest recorded R254 submit gate preview exists and is valid.
- Latest R253B fresh-context signed request exists and is valid.
- Signed request was created by R253B.
- Signed request timestamp freshness is checked with a 60 second real-submit window.
- Runtime credential source readiness is summarized without printing or persisting secrets.
- Kill switch, lane controls, and live execution flags are checked read-only.
- Endpoint allowlist is exactly `POST /fapi/v1/order`.
- Exactly three orders are intended in sequence: main, stop, take-profit.
- Idempotency blocks duplicate live submit records for the same lane/signed artifact.
- Tiny-live risk contract bounds are checked read-only.
- Post-submit reconciliation requirements are included in the output packet.

## Safety

R255 preserves:

- `submit_allowed=false`
- `actual_submit_executed=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `network_allowed=false`
- `secrets_shown=false`
- `secrets_persisted=false`
- no env/config/lane-control mutation

The module exposes `execute_actual_submit_with_injected_client` for mocked unit
tests and future controlled integration only. The CLI does not inject a client
and does not execute live Binance calls.

## Ledger

R255 dry preview records append to:

`logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson`

Real submit records are not appended by the Codex implementation run.

## Next Phase

R256 should be an operator real-submit runbook and reconciliation phase. It
must include the final manual pre-submit checklist, exact command for the
operator to run manually, post-submit reconciliation steps, duplicate review,
partial-acceptance abort handling, and immediate cleanup instructions.
