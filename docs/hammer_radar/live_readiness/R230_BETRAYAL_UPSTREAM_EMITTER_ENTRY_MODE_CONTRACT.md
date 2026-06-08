# R230 Betrayal Upstream Emitter Entry Mode Contract

R230 adds a paper-only future-row contract for betrayal upstream emitter rows. It does not rewrite historical ledgers, append normalized source rows, mutate env/config files, call Binance/network, create order payloads, promote betrayal, or authorize live execution.

## Purpose

R229 proved that downstream propagation cannot rescue most historical rows because `entry_mode` and `lane_key` were not emitted upstream. R230 moves the requirement to the birth point of future betrayal rows.

The contract requires future betrayal source rows to carry:

- `schema_version`
- `source_family`
- `candidate`
- `symbol`
- `timeframe`
- `entry_mode`
- `original_direction`
- `inverse_direction`
- `emitted_direction`
- `source_identity`
- `source_signal_id`
- `source_signal_timestamp`
- `emitted_signal_id`
- `lane_key`
- `betrayal_event_identity`
- `betrayal_event_identity_hash`
- `outcome_windows`
- `paper_only=true`
- `live_authorized=false`
- `promotion_allowed=false`

## Operator Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-upstream-emitter-entry-mode-contract
```

Record contract audit only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-upstream-emitter-entry-mode-contract \
  --record-contract \
  --confirm-betrayal-upstream-emitter-entry-mode-contract "I CONFIRM BETRAYAL UPSTREAM EMITTER ENTRY MODE CONTRACT RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Ledger:

```text
logs/hammer_radar_forward/betrayal_upstream_emitter_entry_mode_contract.ndjson
```

## Safety State

R230 is future contract wiring and audit only:

- No historical ledger rewrite.
- No normalized source row append.
- No env or config mutation.
- No lane mode change.
- No risk contract config write.
- No Binance or network call.
- No order/test-order/protective/transfer/withdraw call.
- No live authorization.
- No betrayal, signal-origin, or lane promotion.
- No tiny-live readiness inference.

## Result Interpretation

`future_emitter_contract_readiness_report.future_rows_can_be_born_complete` means only that inspected future emitter surfaces can be wired to the R230 contract. It does not create resolver-ready historical rows and does not affect BTCUSDT 8m short capture threshold, funding, risk-contract readiness, or live authorization.

R231 should run a local paper-only synthetic future-row smoke using the R230 helper to prove a row can be born complete.
