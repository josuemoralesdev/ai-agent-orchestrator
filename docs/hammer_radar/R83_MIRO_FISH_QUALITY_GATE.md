# R83 Miro Fish Quality Gate

## Purpose

R83 adds a local Miro Fish Quality Gate for Hammer Radar candidates. It is a deterministic committee evaluator that scores normal and betrayal candidates using local evidence only:

- strategy performance and live-eligibility recommendations
- R80/R80.2 betrayal audit evidence
- R81 true inverse validation status
- R82 Markov regime gate output
- candle archive availability
- timestamp-alignment and resolver integrity summaries
- operator safety fields

R83 is read-only quality scoring. It does not place orders, approve live trading, call Binance live/trading endpoints, expose secrets, edit env files, or restart services.

## Local Committee Only

R83 is not the full external MiroFish engine. It does not use an external account, API key, LLM call, cloud simulator, or new heavy dependency.

The full MiroFish simulator can be handled later as a separate project-wide engine. This repo gets a lightweight local committee-inspired evaluator only.

## Why R83 Follows R82

R82 added regime context after R81.4 fixed unsafe timestamp alignment. R83 uses that regime context as one committee vote, then combines it with evidence quality, risk availability, betrayal validation, data integrity, and operator readability.

R83 does not replace:

- the normal 13m/44m promotion path
- R81 true inverse validation for betrayal candidates
- future funding checks
- protective order checks
- exact operator approval
- live execution gates

## Committee Fish

R83 uses six deterministic fish evaluators.

### Evidence Fish

Evaluates source recommendation, sample count, and whether the candidate has enough historical evidence.

### Regime Fish

Uses R82 Markov Regime Gate:

- regime support becomes `FISH_PASS`
- regime rejection becomes `FISH_REJECT`
- neutral or pending regime becomes `FISH_WARN`

### Risk Fish

Checks whether explicit entry, stop, and take-profit fields are available. Missing risk fields return `FISH_WARN`, not pass.

### Betrayal Fish

Applies to betrayal candidates. If true inverse validation is pending, or aggregate betrayal direction is still contextual, the vote is `FISH_BLOCKED`.

### Data Integrity Fish

Checks candle archive availability and R81 invalid resolution counts. If invalid persisted resolution records are present, this fish blocks the candidate.

### Operator Fish

Checks that the candidate has clear identity and source-path fields for operator review.

## Vote Statuses

- `FISH_PASS`
- `FISH_WARN`
- `FISH_REJECT`
- `FISH_INSUFFICIENT_DATA`
- `FISH_BLOCKED`

Deterministic score weights:

```text
PASS = +2
WARN = +1
INSUFFICIENT_DATA = 0
REJECT = -2
BLOCKED = hard block
```

## Final Quality Statuses

- `MIRO_FISH_SUPPORTS_CANDIDATE`
- `MIRO_FISH_OPERATOR_REVIEW_ONLY`
- `MIRO_FISH_NEEDS_MORE_EVIDENCE`
- `MIRO_FISH_REJECTS_CANDIDATE`
- `MIRO_FISH_BLOCKED`

Rules:

- any `FISH_BLOCKED` -> `MIRO_FISH_BLOCKED`
- any `FISH_REJECT` -> `MIRO_FISH_REJECTS_CANDIDATE`
- betrayal with pending true inverse validation cannot be supported
- insufficient evidence -> `MIRO_FISH_NEEDS_MORE_EVIDENCE`
- strong normal evidence plus supportive regime and clean integrity can become `MIRO_FISH_SUPPORTS_CANDIDATE`
- mixed non-critical results -> `MIRO_FISH_OPERATOR_REVIEW_ONLY`

## Candidate Handling

Normal candidates come from the existing strategy performance live-eligibility matrix and R82 gates. The 13m long `ladder_close_50_618` path can receive local committee support when evidence, regime, integrity, and operator checks pass.

44m long candidates can be regime-supported but still fail strong support when source evidence is insufficient.

Betrayal candidates come from R80.2/R81/R82. Aggregate 222m, 55m, and 88m candidates remain blocked from strong support while true inverse validation is pending and aggregate direction is only contextual.

Direction/entry-mode betrayal candidates cannot bypass the true inverse pending blocker.

## No-Live Guarantees

R83 payloads keep:

```text
live_execution_enabled=false
allow_live_orders=false
global_kill_switch=true
order_placed=false
real_order_placed=false
execution_attempted=false
order_payload_created=false
network_allowed=false
secrets_shown=false
```

`MIRO_FISH_SUPPORTS_CANDIDATE` means local committee support for operator review only. It is not live approval.

## Smoke Commands

CLI:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  miro-fish-quality-gate
```

Related regime context:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  markov-regime-gate
```

Related betrayal validation:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-inverse-validation
```

API when the local service is already running:

```text
curl -s http://127.0.0.1:8015/strategy-performance/miro-fish-quality-gate | jq '
{
  status,
  phase,
  execution_mode,
  committee,
  top_supported_candidates,
  operator_review_candidates,
  blocked_or_rejected_candidates,
  live_execution_enabled,
  allow_live_orders,
  global_kill_switch,
  order_placed,
  real_order_placed,
  execution_attempted,
  network_allowed,
  secrets_shown
}'
```

## Next Phase Recommendation

R84 should address Live Funding + Final Execution Arming only after quality review is clean. R84 must remain explicit, operator-approved, and gated by funding checks, protective stop/take-profit requirements, exact approval language, kill-switch state, and live-execution environment controls.
