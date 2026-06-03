# R178 Risk Contract Apply Packet If Evidence Ready

R178 adds a local-only risk-contract apply packet for `BTCUSDT|8m|short|ladder_close_50_618`.

It composes R177 evidence threshold state, the R161 risk-contract draft preview, and the R162 apply-review state into a future config patch preview. The packet is blocked unless evidence, funding, and operator confirmation are all ready.

R178 does not write env/config files, write lane controls, write risk-contract config, call Binance, create payloads, place orders, transfer, withdraw, enable live flags, disable the kill switch, set the short lane `tiny_live`, or authorize live execution.

## Scope

R178 adds:

- `src/app/hammer_radar/operator/risk_contract_apply_packet_8m_short.py`
- `risk-contract-apply-packet-8m-short` in `src.app.hammer_radar.operator.inspect`
- `logs/hammer_radar_forward/risk_contract_apply_packets_8m_short.ndjson` as an append-only packet ledger after exact confirmation

The packet reads local config and ledger surfaces only:

- `configs/hammer_radar/lane_controls.json`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `evidence_threshold_recheck_8m_short.ndjson`
- `short_risk_contract_draft_previews.ndjson`
- `short_risk_contract_apply_reviews.ndjson`

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  risk-contract-apply-packet-8m-short
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  risk-contract-apply-packet-8m-short \
  --record-packet \
  --confirm-risk-contract-apply-packet "wrong"
```

Record packet only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  risk-contract-apply-packet-8m-short \
  --record-packet \
  --confirm-risk-contract-apply-packet "I CONFIRM RISK CONTRACT APPLY PACKET RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Output

The command reports:

- `evidence_gate.fresh_capture_count`
- `evidence_gate.required_fresh_capture_count=10`
- `evidence_gate.threshold_met`
- `funding_gate.funding_status`
- `funding_gate.available_balance_usdt`
- `funding_gate.funding_ready`
- `risk_contract_draft.candidate_id`
- `risk_contract_draft.target_contract_exists`
- `future_config_patch_preview.would_write_config_now=false`
- `future_config_patch_preview.preview_only=true`
- `apply_packet_readiness`
- `blockers`
- `future_apply_conditions`
- `recommended_next_operator_move`

## Readiness Semantics

- `APPLY_PACKET_BLOCKED_BY_EVIDENCE`: unique fresh captures are below 10.
- `APPLY_PACKET_BLOCKED_BY_FUNDING`: evidence is ready, but funding is not ready.
- `APPLY_PACKET_BLOCKED_BY_OPERATOR_APPROVAL`: evidence and funding are ready, but operator approval is absent.
- `APPLY_PACKET_BLOCKED_BY_MULTIPLE_GATES`: multiple non-evidence/funding/approval conditions require manual review.
- `APPLY_PACKET_READY_FOR_FUTURE_CONFIG_REVIEW`: all packet gates are satisfied for a future config-review phase only.
- `UNKNOWN_NEEDS_MANUAL_REVIEW`: the target surface is malformed or outside the expected short paper lane.

With the current known 3/10 capture state, R178 should return `RISK_CONTRACT_APPLY_PACKET_BLOCKED` and `APPLY_PACKET_BLOCKED_BY_EVIDENCE`.

## Do Not Run Yet

- `live-connector-submit`
- any order endpoint
- global live flag arming
- kill switch disable
- set short lane `tiny_live`
- write risk contract config
- transfer
- withdraw

## Safety Boundary

R178 safety remains:

- `env_written=false`
- `env_mutated=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `lane_config_written=false`
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
- `transfer_endpoint_called=false`
- `withdraw_endpoint_called=false`
- `secrets_shown=false`
- `global_live_flags_changed=false`
- `kill_switch_disabled=false`
- `paper_live_separation_intact=true`

## Next Phase

R179 should apply risk-contract config only if evidence threshold is met, funding is ready, operator confirmation is explicit, tests pass, and the phase remains no-live/no-lane-mode-change/no-Binance/no-order.
