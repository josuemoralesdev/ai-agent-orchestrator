# R263 Tiny-Live Final Submit Console And Arming

Build the final submit console after R262B contract-fit regeneration and R261
control arming.

Scope:
- Consume the latest R261 controls arming result from
  `logs/hammer_radar_forward/tiny_live_controls_arming.ndjson`.
- Consume the latest R262A risk-contract fix/recheck result from
  `logs/hammer_radar_forward/tiny_live_risk_contract_fix.ndjson`.
- Consume the latest R262B percentage risk-contract fit result from
  `logs/hammer_radar_forward/tiny_live_percentage_risk_contract_fit.ndjson`.
- Require R262B risk contract fit valid for
  `BTCUSDT|8m|short|ladder_close_50_618`.
- Require R261 controls arming recorded after the R262B review for
  `BTCUSDT|8m|short|ladder_close_50_618`.
- Require the latest R255 dry preview to validate the regenerated R253B triplet
  against the percentage-resolved risk contract.
- Show the final signed triplet from the latest fresh signed request.
- Show the regenerated main quantity; do not assume `0.007 BTC`.
- Show signed request freshness age and stale/regeneration blockers.
- Show all blockers from R255/R260/R261/R262A/R262B, including risk contract
  validity, lane controls, live execution, kill switch, duplicate-submit, and
  reconciliation state.
- Show the exact manual submit command and exact submit confirmation phrase
  generated from the latest signed triplet quantity.
- Default to no submit.
- No auto-submit by default.
- No automatic Binance order call.
- No order placement by default.
- Preserve duplicate-submit and reconciliation checks.
- Keep R263 as an operator final console unless a later explicit phase
  authorizes a controlled submit action.
