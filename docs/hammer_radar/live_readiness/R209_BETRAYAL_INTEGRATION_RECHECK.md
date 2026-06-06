# R209 Betrayal Integration Recheck

R209 is a paper-only audit integration recheck for betrayal/inverse evidence.
It exists because recent strategy, ranking, readiness, and fisherman surfaces can
forget historical betrayal evidence when the phase does not name it explicitly.

## Scope

- Primary historical candidate: `222m aggregate`
- Watchlist candidate: `88m aggregate`
- Current capture linkage: `BTCUSDT|222m|long|ladder_close_50_618` when present in local R198/R208A ledgers
- Output ledger: `logs/hammer_radar_forward/betrayal_integration_recheck.ndjson`

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-integration-recheck
```

Record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-integration-recheck \
  --record-recheck \
  --confirm-betrayal-integration-recheck "I CONFIRM BETRAYAL INTEGRATION RECHECK RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Findings Model

R209 separates:

- naive inverse audit evidence from R80
- true inverse paper validation from R81/R96-R100 ledgers
- regime support from R82
- Miro Fish quality from R83
- current matrix integration from R203/R205/R206
- live readiness, which remains false

The latest 222m full-spectrum capture can link to the R80 222m aggregate
timeframe, but it cannot be counted as a validated true inverse sample until a
local event matcher and true inverse outcome resolver prove the outcome.

## Safety State

R209 does not call Binance or the network. It does not create order payloads,
write env/config/risk/lane/scoring/matrix state, promote signal origins or
lanes, disable the kill switch, set any lane to `tiny_live`, or authorize live
execution.

Expected safety result:

- `env_written=false`
- `config_written=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `network_allowed=false`
- `secrets_shown=false`
- `paper_live_separation_intact=true`
- `betrayal_live_authorized=false`
- `betrayal_promoted=false`

## Recommendations

- Keep betrayal audit-only in R209.
- Run R210 to refresh true inverse paper validation using local evidence only.
- Add a betrayal-aware paper matrix row later only after true inverse refresh.
- Do not promote betrayal.
- Do not live-authorize betrayal.
