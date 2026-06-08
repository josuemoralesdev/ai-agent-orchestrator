# R238 Betrayal Ranking Feed Preview

R238 prepares the betrayal ranking/performance feed contract from R237 true-inverse capture rows. It is preview-only: it does not append normal ranking, strategy performance, strategy promotion, or paper outcome ledgers, and it does not promote betrayal or authorize live execution.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-ranking-feed-preview
```

Record the preview audit ledger only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-ranking-feed-preview \
  --record-ranking-preview \
  --confirm-betrayal-ranking-feed-preview "I CONFIRM BETRAYAL RANKING FEED PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-ranking-feed-preview \
  --record-ranking-preview \
  --confirm-betrayal-ranking-feed-preview "wrong"
```

## Inputs

R238 reads local evidence only:

- latest R237 `betrayal_true_inverse_outcome_capture_bridge.ndjson`
- latest R236 `betrayal_paper_outcome_tracking_bridge.ndjson`
- latest R235 `betrayal_signal_origin_integration_contract.ndjson`
- strategy ranking context ledgers as read-only schema context
- official tiny-live capture sync for `BTCUSDT|8m|short|ladder_close_50_618`

## Output

The command produces:

- `ranking_feed_preview_rows`
- `ranking_feed_summary`
- `ranking_gap_report`
- `promotion_gate_preview`
- `track_b_structural_completion_report`
- `ranking_feed_recommendations`
- `ranking_overall_status`
- safety flags proving no config, normal ledger, network, order, promotion, or live mutation occurred

The append-only preview ledger is:

```text
logs/hammer_radar_forward/betrayal_ranking_feed_preview.ndjson
```

## Rules

A row can become `RANKING_FEED_PREVIEW_READY` only when it is a betrayal row with ready/trackable true-inverse capture structure, `ranking_projection_ready=true`, valid symbol/timeframe/direction/inverse direction, registry-valid entry mode, lane key, source signal identity, paper outcome tracking identity, true inverse capture identity, and outcome window spec.

If `true_inverse_outcome_found=false`, R238 reports:

- `ranking_evidence_available=false`
- `ranking_score=null`
- `win_rate_pct=null`
- `sample_size=null`
- `promotion_gate_ready=false`
- `promotion_review_ready=false`
- blocker `true_inverse_outcome_pending`

R238 never fabricates true inverse outcomes, ranking scores, win rates, sample size, or promotion eligibility.

## Safety

R238 keeps:

- `ranking_feed_preview_ledger_only=true`
- `normal_ranking_ledger_appended=false`
- `strategy_performance_appended=false`
- `strategy_promotion_status_appended=false`
- `paper_outcomes_appended=false`
- `true_inverse_outcomes_fabricated=false`
- `ranking_scores_fabricated=false`
- `win_rates_fabricated=false`
- `promotion_eligibility_fabricated=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
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

## Current Expected State

With R237 showing 33 ranking-projection-ready rows and zero true inverse outcomes found, R238 should report Track B as structurally complete for now while waiting for data, not architecture. It must not feed ranking or promotion until real true inverse outcomes and computed ranking/performance evidence exist.
