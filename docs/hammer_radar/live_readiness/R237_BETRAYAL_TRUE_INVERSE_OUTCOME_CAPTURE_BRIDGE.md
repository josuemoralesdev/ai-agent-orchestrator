# R237 Betrayal True Inverse Outcome Capture Bridge

R237 wires R236 betrayal paper outcome tracking identities into deterministic true-inverse capture previews. It is paper-only and audit-only: it does not write normal paper outcomes, promote betrayal, change configs, call Binance/network, create order payloads, or authorize live execution.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-true-inverse-outcome-capture-bridge
```

Record the bridge preview audit ledger:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-true-inverse-outcome-capture-bridge \
  --record-capture-bridge \
  --confirm-betrayal-true-inverse-outcome-capture-bridge "I CONFIRM BETRAYAL TRUE INVERSE OUTCOME CAPTURE BRIDGE RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-true-inverse-outcome-capture-bridge \
  --record-capture-bridge \
  --confirm-betrayal-true-inverse-outcome-capture-bridge "wrong"
```

## Inputs

R237 reads local evidence only:

- latest R236 `betrayal_paper_outcome_tracking_bridge.ndjson`
- latest R235 `betrayal_signal_origin_integration_contract.ndjson`
- latest R234 `betrayal_gate_ready_lane_packet.ndjson`
- betrayal true-paper outcome, paper signal, shadow outcome, shadow resolution, normal paper outcome, generic outcome, strategy performance, strategy promotion, and capture-count sync ledgers as read-only context

## Output

The command produces:

- `true_inverse_capture_preview_rows`
- `capture_summary`
- `capture_gap_report`
- `ranking_projection`
- `capture_recommendations`
- `capture_overall_status`
- official tiny-live status for `BTCUSDT|8m|short|ladder_close_50_618`
- safety flags proving no live/config/order/paper-outcome mutation occurred

The append-only audit ledger is:

```text
logs/hammer_radar_forward/betrayal_true_inverse_outcome_capture_bridge.ndjson
```

## Capture Rules

A row is `TRUE_INVERSE_CAPTURE_READY` only when it is a betrayal R236 `BRIDGE_READY` row with:

- `paper_signal_ready=true`
- `paper_outcome_ready=true`
- `outcome_tracking_ready=true`
- `ranking_feed_ready=true`
- symbol, timeframe, original direction, inverse direction, registry-valid entry mode, lane key
- signal id, source signal id, and source identity
- paper outcome tracking identity
- outcome window spec and capture checkpoints
- `paper_only=true`
- `live_authorized=false`
- `promotion_allowed=false`

Existing rows in `betrayal_true_paper_outcomes.ndjson` may be detected by matching capture, paper outcome, signal, source signal, or source identity fields. R237 does not fabricate outcomes and does not append to `paper_outcomes.ndjson`.

`ranking_projection_ready` remains preview-only. It does not imply promotion readiness, risk contract readiness, operator approval, tiny-live readiness, or live authorization.

## Safety

R237 keeps:

- `paper_outcomes_appended=false`
- `paper_outcome_ledger_rewritten=false`
- `true_inverse_outcomes_fabricated=false`
- `capture_bridge_preview_ledger_only=true`
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

R238 should consume R237 preview rows and prepare a betrayal ranking/performance feed preview. R238 must remain paper-only with no config writes, no normal paper outcome writes, no promotion, no Binance/network calls, and no live execution.
