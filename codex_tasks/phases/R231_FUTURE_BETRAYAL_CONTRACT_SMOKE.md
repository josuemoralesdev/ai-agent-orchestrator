# R231 Future Betrayal Contract Smoke

## Phase

R231 Future Betrayal Contract Smoke

## Purpose

Use the R230 upstream emitter entry-mode contract helper to generate or preview a synthetic/local future betrayal source row and prove that future rows can be born complete with:

- registry-valid `entry_mode`
- `lane_key`
- `source_identity`
- `source_signal_id`
- `source_signal_timestamp`
- `original_direction`
- `inverse_direction`
- `emitted_direction`
- `emitted_signal_id`
- `betrayal_event_identity`
- `betrayal_event_identity_hash`
- `paper_only=true`
- `live_authorized=false`
- `promotion_allowed=false`

## Non-Negotiables

- Do not rewrite historical ledgers.
- Do not append normalized source rows.
- Do not write env files.
- Do not write configs.
- Do not write risk contract config.
- Do not change lane modes.
- Do not set any lane `tiny_live`.
- Do not call Binance.
- Do not call network.
- Do not create order payloads.
- Do not place orders.
- Do not promote betrayal.
- Do not promote signal origins or lanes.
- Do not infer tiny-live readiness.
- Do not authorize live execution.

## Expected Implementation

- Reuse `src/app/hammer_radar/operator/betrayal_upstream_emitter_entry_mode_contract.py`.
- Build a local synthetic future betrayal source row with explicit evidence only.
- Validate that `entry_mode` exists in the R218 registry and is not `unknown` or `entry_unknown`.
- Validate that `lane_key` is built only from `symbol`, `timeframe`, `emitted_direction`, and `entry_mode`.
- Validate that `emitted_direction == inverse_direction`.
- Emit preview/report evidence only.

## Validation

Run focused tests for the R231 smoke surface plus R230:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_betrayal_upstream_emitter_entry_mode_contract.py
```

R231 must include safety assertions proving:

- `env_written=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `lane_config_written=false`
- `historical_rows_rewritten=false`
- `normalized_rows_appended=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `binance_order_endpoint_called=false`
- `network_allowed=false`
- `transfer_endpoint_called=false`
- `withdraw_endpoint_called=false`
- `betrayal_live_authorized=false`
- `betrayal_promoted=false`
- `future_contract_only=true`
