# R262 Tiny-Live Final Submit Console

Build the final submit console after R262A risk-contract recheck and R261/R262A
control arming.

Scope:
- Consume the latest R261 controls arming result from
  `logs/hammer_radar_forward/tiny_live_controls_arming.ndjson`.
- Consume the latest R262A risk-contract fix/recheck result from
  `logs/hammer_radar_forward/tiny_live_risk_contract_fix.ndjson`.
- Require R262A risk contract valid for
  `BTCUSDT|8m|short|ladder_close_50_618`.
- Require R261 controls arming recorded for
  `BTCUSDT|8m|short|ladder_close_50_618`.
- Require R260 fresh cycle valid.
- Show the final signed triplet from the latest fresh signed request.
- Show signed request freshness age and stale/regeneration blockers.
- Show all blockers from R255/R260/R261, including risk contract validity,
  lane controls, live execution, kill switch, duplicate-submit, and
  reconciliation state.
- Show the exact manual submit command and exact submit confirmation phrase.
- Default to no submit.
- No auto-submit by default.
- No automatic Binance order call.
- No order placement by default.
- Preserve duplicate-submit and reconciliation checks.
- Keep R262 as an operator final console unless a later explicit phase
  authorizes a controlled submit action.
