# R236 Betrayal Paper Outcome Tracking Bridge

R236 wires R235 betrayal signal-origin preview rows into a paper-only outcome tracking bridge. It does not write normal paper outcomes, promote betrayal, change configs, call Binance/network, create order payloads, or authorize live execution.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-paper-outcome-tracking-bridge
```

Record the bridge preview audit ledger:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-paper-outcome-tracking-bridge \
  --record-bridge \
  --confirm-betrayal-paper-outcome-tracking-bridge "I CONFIRM BETRAYAL PAPER OUTCOME TRACKING BRIDGE RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-paper-outcome-tracking-bridge \
  --record-bridge \
  --confirm-betrayal-paper-outcome-tracking-bridge "wrong"
```

## Inputs

R236 reads local evidence only:

- latest R235 `betrayal_signal_origin_integration_contract.ndjson`
- latest R234 `betrayal_gate_ready_lane_packet.ndjson`
- paper outcome, generic outcome, strategy performance, strategy promotion, betrayal paper signal, betrayal true-paper outcome, and capture sync ledgers as schema/context only

## Output

The command produces:

- `bridge_preview_rows`
- `bridge_summary`
- `bridge_gap_report`
- `bridge_promotion_path`
- `bridge_recommendations`
- `bridge_overall_status`
- official tiny-live status for `BTCUSDT|8m|short|ladder_close_50_618`
- safety flags proving no live/config/order action occurred

The append-only audit ledger is:

```text
logs/hammer_radar_forward/betrayal_paper_outcome_tracking_bridge.ndjson
```

## Bridge Rules

A row is `BRIDGE_READY` only when it is a betrayal same-flow preview row with:

- `paper_signal_ready=true`
- `paper_outcome_ready=true`
- symbol, timeframe, direction, registry-valid entry mode, lane key
- signal id and source signal id
- source identity
- paper outcome tracking identity
- outcome window spec
- `paper_only=true`
- `live_authorized=false`
- `promotion_allowed=false`

`outcome_tracking_ready`, `ranking_feed_ready`, and `promotion_gate_preview` remain preview-only. They do not imply live readiness, promotion, risk contract readiness, or operator approval.

Rows can still require true inverse/paper outcome evidence after bridge readiness. R236 reports that gap for R237 but does not create or backfill outcomes.

## Safety

R236 keeps:

- `paper_outcomes_appended=false`
- `paper_outcome_ledger_rewritten=false`
- `bridge_preview_ledger_only=true`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `network_allowed=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `lane_config_written=false`
- `fisherman_config_written=false`
- `scheduler_config_written=false`
- `signal_origin_promoted=false`
- `lane_promoted=false`
- `betrayal_promoted=false`
- `betrayal_live_authorized=false`
- official tiny-live lane unchanged

## Next

R237 should capture or bridge true inverse outcomes for betrayal-tagged paper outcome identities. It must remain paper-only with no config writes, no promotion, no Binance/network calls, and no live execution.
