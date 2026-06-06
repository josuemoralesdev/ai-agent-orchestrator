# R211 Betrayal Paper Matrix Context

## Purpose

Add betrayal-aware paper matrix context using R210 betrayal true-inverse refresh
output.

## Required Behavior

- Read `logs/hammer_radar_forward/betrayal_true_inverse_refresh.ndjson`.
- Read R210 preview output when no record exists.
- Add betrayal context only as paper/readiness review context.
- If true inverse validation is still pending, keep betrayal blocked and
  context-only.
- Separate naive inverse audit evidence from refreshed true-inverse samples.
- Preserve `222m aggregate`, `88m aggregate`, and optional `55m aggregate`
  context.

## Safety

R211 must not write config, mutate env, call Binance/network, create order
payloads, place orders, promote betrayal, promote any signal origin/lane, set
any lane to `tiny_live`, disable the kill switch, or authorize live execution.

## Expected Output

- Paper-only betrayal matrix context summary.
- Explicit blocked/context-only status when R210 has no validated samples.
- Recommended next phase, likely R212 if deterministic tracking is still needed.
