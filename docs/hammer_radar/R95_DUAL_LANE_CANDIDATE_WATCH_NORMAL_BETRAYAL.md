# R95 Dual-Lane Candidate Watch: Normal + Betrayal

R95 adds a read-only dual-lane watch surface for BTCUSDT candidate review.

Lane A keeps watching the current normal candidate:

```text
normal|BTCUSDT|13m|long|ladder_close_50_618
```

Lane B brings the R80 betrayal audit back as a parallel audit lane. Betrayal evidence is explicitly audit-only until actual inverse paper entries, exits, stops, take-profits, and outcomes are tracked.

R95 does not place orders, sign payloads, create executable exchange payloads, call Binance, check balances, modify env files, restart services, disable the kill switch, or enable live execution.

## Why R95 Follows R94

R94 confirmed the normal lane remains present but support is not restored:

- Miro Fish remains `MIRO_FISH_OPERATOR_REVIEW_ONLY`
- Markov remains neutral or contextual for the candidate
- strategy inputs remain acceptable for review
- `support_restored=false`

That makes the correct next step a watch loop, not execution. R95 broadens the watch to compare the normal lane against betrayal audit opportunities without promoting either lane into live readiness.

## Normal Lane

The normal lane consumes the R94 candidate revalidation watch and reports:

- candidate presence
- Miro Fish status and score
- Markov regime and gate
- strategy inputs
- support restoration state
- normal lane readiness class
- next action

Normal support is restored only when current R94 support is restored. R95 does not force Miro Fish or Markov.

## Betrayal Lane

The betrayal lane consumes the R80 betrayal strategy audit:

- timeframe aggregate primary candidates
- timeframe aggregate watchlist candidates
- direction/entry-mode primary candidates
- direction/entry-mode watchlist candidates
- rejected count
- ranked top betrayal candidates

Every betrayal candidate is labeled:

```text
NAIVE_INVERSE_AUDIT_EVIDENCE_ONLY
```

until true inverse paper tracking exists.

## Audit Evidence vs True Paper Evidence

R80 betrayal rows are naive inverse audit evidence. A weak original strategy can imply a strong inverse hypothesis, but that is not the same thing as a paper strategy with recorded inverse entries and exits.

R95 requires betrayal maturation before any later review packet:

- create betrayal paper signal identity
- track actual inverse entries/exits
- record stop/take-profit behavior
- collect minimum samples
- evaluate with Miro Fish/Markov equivalent
- only then consider a risk contract

## Why Betrayal Is Not Live-Ready

Betrayal candidates can lead as audit opportunities, not as tradeable candidates.

R95 never treats `BETRAYAL_PRIMARY_CANDIDATE` or `BETRAYAL_WATCHLIST` as live-ready. Betrayal rows have:

- `true_paper_required=true`
- `live_ready=false`
- `maturity_status=NEEDS_TRUE_PAPER_TRACKING`

## Operator/Architect Seat

The Operator/Architect Seat is advisory only. It may recommend:

- waiting for normal Markov/Miro Fish support restoration
- opening a betrayal maturation lane
- no live action

It cannot override Miro Fish, Markov, R84, R87, R89, or execution gates.

## Surfaces

API:

```text
GET /live-arming/dual-lane-candidate-watch
POST /live-arming/dual-lane-candidate-watch/report
```

CLI:

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward dual-lane-candidate-watch
```

Optional scheduler task:

```text
dual_lane_candidate_watch
```

The scheduler task is available but not part of `DEFAULT_TASKS`. It runs dry-run/no-write by default.

## Smoke Commands

```bash
.venv/bin/python -m compileall src/app/hammer_radar
.venv/bin/python -m pytest tests/hammer_radar/test_betrayal_strategy_audit.py -q
.venv/bin/python -m pytest tests/hammer_radar/test_strategy_performance.py tests/hammer_radar/test_approval_api.py tests/hammer_radar/test_inspect.py tests/hammer_radar/test_paper_refresh_scheduler.py -q
.venv/bin/python -m pytest tests/hammer_radar -q
git diff --check
```

Local CLI inspection:

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward dual-lane-candidate-watch | sed -n '1,360p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward candidate-revalidation-watch | sed -n '1,260p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-strategy-audit | sed -n '1,220p'
```

API smoke checks are only appropriate if the local service is already running. R95 does not require a service restart for local code validation.

## Next Phase Recommendation

If current betrayal audit evidence exists:

```text
R96 Betrayal True Paper Tracking Scaffold
```

If no current betrayal candidates exist:

```text
R96 Markov Support Watch Scheduler / Candidate Revalidation Loop
```

Both remain non-executable unless a later explicit phase defines a separate, human-approved, safety-gated path.

R96 created deterministic betrayal paper identities. R97 follows by adding a local paper outcome ledger and read-only tracking loop; this does not change R95's no-live, no-order, no-payload boundary.
