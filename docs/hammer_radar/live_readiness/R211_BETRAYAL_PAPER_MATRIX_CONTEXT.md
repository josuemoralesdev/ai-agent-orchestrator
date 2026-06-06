# R211 Betrayal Paper Matrix Context

R211 adds betrayal/inverse evidence to the paper matrix stack as context only.
It reads the R210 true-inverse refresh, R209 integration recheck, R205 pattern
lane matrix, R203 anchor/signal confluence matrix, and R206 tiny-live readiness
gap recheck from local ledgers. It does not change scoring configs, lane modes,
risk contracts, registry definitions, live flags, or environment files.

## Scope

- Primary betrayal context: `222m aggregate`
- Watchlist betrayal context: `88m aggregate`
- Optional historical context: `55m aggregate` when refreshed true-inverse
  samples exist
- Output ledger: `logs/hammer_radar_forward/betrayal_paper_matrix_context.ndjson`
- Normal references: `8m short + hammer_wick_reversal`,
  `8m short + bearish_engulfing`, and `8m short + three_black_crows`

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-paper-matrix-context
```

Record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-paper-matrix-context \
  --record-matrix \
  --confirm-betrayal-paper-matrix-context "I CONFIRM BETRAYAL PAPER MATRIX CONTEXT RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-paper-matrix-context \
  --record-matrix \
  --confirm-betrayal-paper-matrix-context "wrong"
```

## Context Model

R211 creates betrayal context rows from refreshed true-inverse sample depth,
validation status, original failure profile, candle/timeframe coverage,
unresolved shadow samples, regime/Miro Fish availability, and integration
readiness. The score is paper-only and cannot promote a signal origin, promote a
lane, infer tiny-live readiness, or create live permission.

Expected rows:

- `222m aggregate`: primary betrayal candidate, true-inverse refreshed, not
  live-ready
- `88m aggregate`: betrayal watchlist, true-inverse refreshed, not live-ready
- `55m aggregate`: optional historical watchlist when refreshed samples exist,
  not live-ready

## Gaps

R211 intentionally keeps these blockers visible:

- deterministic betrayal event tracker is missing
- regime gate support is missing or pending
- Miro Fish quality support is missing or pending
- aggregate direction split is missing
- betrayal remains excluded from tiny-live readiness

## Safety State

R211 does not call Binance or the network. It does not create order payloads,
write env/config/risk/lane/registry/scoring/matrix state, promote betrayal,
disable the kill switch, set any lane to `tiny_live`, transfer, withdraw, or
authorize live execution.

Expected safety result:

- `env_written=false`
- `env_mutated=false`
- `config_written=false`
- `registry_config_written=false`
- `scoring_config_written=false`
- `matrix_config_written=false`
- `risk_contract_config_written=false`
- `lane_config_written=false`
- `ledger_rewritten=false`
- `destructive_write=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `signed_order_request_created=false`
- `signed_trading_request_created=false`
- `signed_readonly_request_created=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `network_allowed=false`
- `transfer_endpoint_called=false`
- `withdraw_endpoint_called=false`
- `secrets_shown=false`
- `global_live_flags_changed=false`
- `kill_switch_disabled=false`
- `paper_live_separation_intact=true`
- `live_authorization_created=false`
- `signal_origin_promoted=false`
- `lane_promoted=false`
- `betrayal_live_authorized=false`
- `betrayal_promoted=false`
- `position_permission_created=false`

## Recommendations

- R212 should build deterministic betrayal event tracking.
- R213 should recheck current regime and Miro Fish quality for betrayal
  candidates as paper-only context.
- Keep weekend/full-spectrum paper fishing running.
- Do not promote betrayal.
- Do not live-authorize betrayal.
