# R177 Evidence Threshold Recheck for BTCUSDT 8m Short

R177 adds a local-only evidence threshold recheck for `BTCUSDT|8m|short|ladder_close_50_618`.

It composes R176 fresh capture count and watcher state, R158 short evidence readiness, R174 funding context, and R162 risk-contract apply-review context into the shortest safe next move after the 10-capture threshold.

R177 does not write env/config files, write lane controls, write risk-contract config, call Binance, create payloads, place orders, transfer, withdraw, enable live flags, disable the kill switch, set the short lane `tiny_live`, or authorize live execution.

## Scope

R177 adds:

- `src/app/hammer_radar/operator/evidence_threshold_recheck_8m_short.py`
- `evidence-threshold-recheck-8m-short` in `src.app.hammer_radar.operator.inspect`
- `logs/hammer_radar_forward/evidence_threshold_recheck_8m_short.ndjson` as an append-only recheck ledger after exact confirmation

The recheck reads local ledgers and existing readonly builders:

- `short_paper_evidence_capture.ndjson`
- `capture_count_sync_8m_short.ndjson`
- `short_evidence_recheck_packets.ndjson`
- `funding_gate_role_specific_sync.ndjson`
- `short_risk_contract_apply_reviews.ndjson`

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  evidence-threshold-recheck-8m-short
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  evidence-threshold-recheck-8m-short \
  --record-recheck \
  --confirm-evidence-threshold-recheck "wrong"
```

Record with exact confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  evidence-threshold-recheck-8m-short \
  --record-recheck \
  --confirm-evidence-threshold-recheck "I CONFIRM EVIDENCE THRESHOLD RECHECK RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Output

The command reports:

- `capture_threshold_state.fresh_capture_count`
- `capture_threshold_state.required_fresh_capture_count=10`
- `capture_threshold_state.threshold_met`
- `capture_threshold_state.unique_captured_signal_ids`
- `capture_threshold_state.latest_captured_signal_id`
- `capture_threshold_state.watcher_likely_running`
- `capture_threshold_state.watcher_stale`
- `short_evidence_state.latest_recheck_status`
- `short_evidence_state.evidence_ready_for_review`
- `funding_context.funding_status`
- `funding_context.available_balance_usdt`
- `funding_context.funding_ready`
- `risk_contract_context.target_contract_exists`
- `risk_contract_context.risk_contract_applied`
- `readiness`
- `blockers`
- `next_safe_path`
- `recommended_next_operator_move`

## Readiness Semantics

- `EVIDENCE_THRESHOLD_NOT_MET`: unique fresh captures are below 10.
- `EVIDENCE_THRESHOLD_MET_FUNDING_BLOCKED`: captures and R158 evidence are ready, but funding is not ready.
- `EVIDENCE_THRESHOLD_MET_RISK_CONTRACT_BLOCKED`: captures, R158 evidence, and funding are ready, but the target risk contract is not applied.
- `EVIDENCE_THRESHOLD_MET_READY_FOR_REVIEW_PACKET`: captures, evidence, funding, and risk-contract context are ready for the next review packet path only.
- `UNKNOWN_NEEDS_MANUAL_REVIEW`: the threshold is met, but R158 evidence is not ready or has missing fields.

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

R177 safety remains:

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

R178 should build a risk-contract apply packet only if evidence is ready. It must remain preview-only by default, must not write config unless a future phase explicitly authorizes it, and must not enable live execution or place orders.
