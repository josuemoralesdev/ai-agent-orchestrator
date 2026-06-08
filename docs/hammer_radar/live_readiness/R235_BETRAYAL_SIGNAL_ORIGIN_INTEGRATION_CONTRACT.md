# R235 Betrayal Signal-Origin Integration Contract

R235 makes betrayal a paper-only signal-origin contract and preview surface. It does not promote betrayal, change the official tiny-live lane, write configs, rewrite historical ledgers, append normalized source rows, call Binance/network, create order payloads, or authorize live execution.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-signal-origin-integration-contract
```

Record the contract-only audit ledger:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-signal-origin-integration-contract \
  --record-contract \
  --confirm-betrayal-signal-origin-integration-contract "I CONFIRM BETRAYAL SIGNAL ORIGIN INTEGRATION CONTRACT RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-signal-origin-integration-contract \
  --record-contract \
  --confirm-betrayal-signal-origin-integration-contract "wrong"
```

## Contract

R235 defines `betrayal_signal_origin_contract_v1`:

- `signal_origin_family="betrayal"`
- `allowed_signal_origin_types=["inverse", "aggregate", "shadow"]`
- `allowed_signal_origin_variants=["betrayal_inverse", "betrayal_aggregate", "betrayal_shadow"]`
- required paper signal fields: symbol, timeframe, direction, registry-valid entry mode, lane key, signal identity, source identity, and paper-only state
- required paper outcome fields: paper signal fields plus outcome tracking identity and outcome window spec
- required ranking fields: paper outcome fields plus enough join fields for performance/ranking
- promotion gate fields: explicit blockers, `live_authorized=false`, and `promotion_allowed=false`

`live_ready_today` is always false.

## Inputs

R235 reads the latest local evidence only:

- R234 betrayal gate-ready lane packet
- R233 capture priority rebalance
- R230 upstream emitter entry-mode contract
- R229 entry-mode source propagation
- R227 direction completion
- existing paper outcome, ranking, promotion, lane score, and enrichment ledgers for schema context

## Output

The command produces:

- `betrayal_signal_origin_contract`
- `same_flow_readiness_rows`
- `same_flow_summary`
- `betrayal_integration_gap_report`
- `betrayal_promotion_path_requirements`
- `betrayal_integration_recommendations`
- `integration_status`
- safety flags proving no live/config/order action occurred

The append-only audit ledger is:

```text
logs/hammer_radar_forward/betrayal_signal_origin_integration_contract.ndjson
```

## Readiness Rules

A row is `paper_signal_ready` only when it has:

- betrayal family
- symbol and timeframe
- direction
- registry-valid entry mode
- lane key
- signal/source signal identity
- source identity
- `paper_only=true`

A row is `paper_outcome_ready` only when it is paper-signal ready and has outcome tracking identity plus an outcome window spec.

`ranking_ready` allows later ranking/performance integration. It does not imply promotion.

`promotion_gate_ready` only means blockers are explicit and the future gate path is known. It does not imply live authorization.

## Safety

R235 keeps:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `binance_order_endpoint_called=false`
- `network_allowed=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `lane_config_written=false`
- `paper_outcome_ledger_rewritten=false`
- `signal_origin_promoted=false`
- `lane_promoted=false`
- `betrayal_promoted=false`
- `betrayal_live_authorized=false`
- official tiny-live lane unchanged: `BTCUSDT|8m|short|ladder_close_50_618`

## Next

R236 should wire betrayal signal-origin preview rows into paper outcome tracking identity. It must remain paper-only with no config writes, no promotion, no Binance/network calls, and no live execution.
