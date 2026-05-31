# R156 Short Strategy Packet Or Top Lane Promotion Review

## Phase

`R156`

## Branch

`r156-short-strategy-packet-or-top-lane-promotion-review`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): EXTENSION OF EXISTING CAPABILITY, WIRING / INTEGRATION, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R155 chooses the next candidate door from full-spectrum paper, betrayal/inverse, direction/timeframe, and incumbent tiny-live evidence. R156 should turn that selected door into a review packet only.

## Main Objective

Build one review packet path based on the R155 recommendation:

- If the best door is short, build a short strategy packet.
- If the best door is long, build a top-lane promotion packet.
- If incumbent tiny-live lanes are flagged, build an incumbent review packet.

No lane mode change or live execution is authorized.

## Short Door Requirements

If R155 recommends a short family:

- Treat the golden pocket as resistance/retrace zone.
- Include short-specific stop/TP review.
- Include paper evidence thresholds.
- Include betrayal/inverse evidence, but prevent low-sample inverse advantage from dominating.
- Keep all short lanes paper-only.
- Require future explicit operator approval for any tiny-live short proposal.

## Long Door Requirements

If R155 recommends a long family:

- Summarize evidence for the top long paper lane.
- Review risk contract fit.
- Review sample quality, win rate, average PnL, stop dominance, and freshness.
- Do not change lane mode without a later explicit operator approval phase.

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order, test-order, protective, account, or private endpoints.
- Do not create executable order payloads.
- Do not create protective payloads.
- Do not sign requests.
- Do not mutate env files.
- Do not mutate lane config.
- Do not set any lane to `tiny_live`.
- Do not set any short lane to `tiny_live`.
- Do not disable the kill switch.
- Do not bypass R106/global gates.
- Do not commit, merge, tag, push, deploy, restart services, run `sudo`, or expose secrets.

## Validation

Run focused compile and tests for any new R156 module and CLI. Run related R155/R154 tests when packet logic consumes R155 output.
