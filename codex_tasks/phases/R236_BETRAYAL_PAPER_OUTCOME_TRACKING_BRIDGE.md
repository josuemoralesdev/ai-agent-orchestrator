# R236 Betrayal Paper Outcome Tracking Bridge

## Purpose

Wire R235 betrayal signal-origin preview rows into paper outcome tracking identity so betrayal can be evaluated by the same paper/ranking machinery later.

## Scope

- Read latest R235 `betrayal_signal_origin_integration_contract.ndjson`.
- Read latest betrayal paper signal, shadow outcome, true paper outcome, and normal paper outcome ledgers.
- Build a preview-only bridge from each paper-signal-ready betrayal row to deterministic paper outcome tracking identity.
- Report rows that can be tracked, rows that need entry mode, rows that need lane key, rows that need source identity, and rows that need source signal identity.
- Do not append normalized source rows.
- Do not rewrite paper outcomes.
- Do not write configs.
- Do not promote betrayal or any signal origin/lane.
- Do not call Binance/network.
- Do not create order payloads.
- Do not authorize live execution.

## Required Safety

R236 must keep:

- `env_written=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `lane_config_written=false`
- `paper_outcome_ledger_rewritten=false`
- `normalized_rows_appended=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `network_allowed=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `signal_origin_promoted=false`
- `lane_promoted=false`
- `betrayal_promoted=false`
- `betrayal_live_authorized=false`
- `live_ready_today=false`

## Expected CLI

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-paper-outcome-tracking-bridge
```

Recording, if implemented, must require an exact confirmation phrase and append only an R236 bridge audit ledger.
