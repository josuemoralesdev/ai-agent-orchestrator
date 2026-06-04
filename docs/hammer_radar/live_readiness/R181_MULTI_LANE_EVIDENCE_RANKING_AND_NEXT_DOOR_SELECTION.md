# R181 Multi-Lane Evidence Ranking and Next Door Selection

R181 adds a local, paper-only ranking surface over R180 multi-lane harvest records, R157/R176 BTCUSDT 8m short capture records, expanded paper watch records, and historical paper outcome/performance records.

It compares the incumbent `BTCUSDT|8m|short|ladder_close_50_618` against expanded paper lanes and reference-only tiny-live incumbents, then selects the next safe candidate door:

- keep 8m short as lead
- switch review attention to another paper lane
- keep harvesting because evidence is insufficient

R181 does not write env/config files, write lane controls, write risk-contract config, call Binance, create order payloads, place orders, transfer, withdraw, enable live flags, disable the kill switch, set any lane `tiny_live`, or authorize live execution.

## Scope

R181 adds:

- `src/app/hammer_radar/operator/multi_lane_evidence_ranking.py`
- `multi-lane-evidence-ranking` in `src.app.hammer_radar.operator.inspect`
- `logs/hammer_radar_forward/multi_lane_evidence_rankings.ndjson`

The ranking reads:

- `logs/hammer_radar_forward/multi_lane_paper_harvester.ndjson`
- `logs/hammer_radar_forward/multi_lane_paper_harvester_heartbeats.ndjson`
- `logs/hammer_radar_forward/short_paper_evidence_capture.ndjson`
- `logs/hammer_radar_forward/expanded_paper_watch.ndjson`
- `logs/hammer_radar_forward/outcomes.ndjson`
- `logs/hammer_radar_forward/paper_executions.ndjson`
- `configs/hammer_radar/lane_controls.json` as read-only lane scope

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  multi-lane-evidence-ranking
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  multi-lane-evidence-ranking \
  --record-ranking \
  --confirm-multi-lane-ranking "wrong"
```

Record ranking:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  multi-lane-evidence-ranking \
  --record-ranking \
  --confirm-multi-lane-ranking "I CONFIRM MULTI LANE EVIDENCE RANKING RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Output

The command reports:

- `ranked_lanes`
- `current_lead`
- `next_door_selection`
- `harvest_summary`
- `blockers`
- `recommended_next_operator_move`
- `recommended_next_engineering_move`
- `do_not_run_yet`
- `safety`

## Scoring Semantics

Fresh captured paper evidence is the primary ranking input. Historical win rate, average PnL, total PnL, paper outcome count, fresh flow, direction pressure, and existing 8m short scaffolding are supporting inputs.

Stale activity adds only a small activity signal and cannot make a lane ready.

Tiny-live incumbent lanes are observed as reference-only rows. They cannot become a new paper candidate door automatically and R181 does not change their mode.

## Safety Boundary

R181 safety remains:

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

R182 should create a signal origin registry and paper-only pattern feed expansion for hammer, three black crows, engulfing, RSI divergence, and golden pocket rejection signals. R182 must not execute live trades or write config.
