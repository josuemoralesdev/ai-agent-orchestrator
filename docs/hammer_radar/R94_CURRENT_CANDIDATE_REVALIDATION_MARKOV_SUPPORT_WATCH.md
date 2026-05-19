# R94 Current Candidate Revalidation + Markov Support Watch

R94 adds a read-only watch surface for the exact BTCUSDT candidate:

```text
normal|BTCUSDT|13m|long|ladder_close_50_618
```

It answers whether the candidate is still present, whether Miro Fish support has returned, whether Markov support has returned, whether strategy-performance inputs remain acceptable, and what must change before later human-record or readiness gates can be reconsidered.

R94 does not place orders, sign payloads, create executable exchange payloads, call Binance, check balances, modify env files, restart services, disable the kill switch, or enable live execution.

## Why R94 Follows R93

R93 repaired R84 preflight blocker hierarchy. R84 now reports `no_supported_miro_fish_candidate` as the primary blocker when no supported candidate is selected, and it reports risk, funding, and operator approval as not evaluated rather than direct blockers.

With R84 hierarchy honest, R94 can focus on the current candidate itself:

- Is the exact candidate present?
- Has Miro Fish returned from `MIRO_FISH_OPERATOR_REVIEW_ONLY` to `MIRO_FISH_SUPPORTS_CANDIDATE`?
- Has Markov moved from `LOW_VOLATILITY / REGIME_NEUTRAL_OR_INSUFFICIENT_DATA` into a supportive regime such as `BULL_TREND` for the long candidate?
- Are strategy inputs still acceptable for review?
- Do R84, R87, R89, and hash-chain facts still keep the system non-executable?

## Current Hash Context

The phase tracks the current local hash-chain values from the R85/R88/R89 snapshot.

The strategic context supplied for R94 is:

- risk contract hash: `3926f7155cbe5551a0781178a7ab79fc3e2dbd2ca8dd82c4914153a47a253c1f`
- packet hash: `c953963a7cd65884fb2124c5f4924ca092ad76caa99699a72593cd340d8273ab`

The implementation does not hardcode those hashes; it surfaces current local continuity from the snapshot.

## Miro Fish Support Restoration

R94 reports:

- `current_miro_fish_status`
- `current_miro_fish_score`
- `source_recommendation`
- `fish_votes`
- `downgrade_reasons`
- `support_restored`
- `support_restoration_requirements`

Support is restored only when current Miro Fish reports `MIRO_FISH_SUPPORTS_CANDIDATE`. R94 never forces that state.

## Markov Support Watch

R94 reports:

- `current_markov_regime`
- `current_markov_gate_status`
- `prior_documented_markov_regime`
- `markov_support_restored`
- `markov_support_required`
- `acceptable_markov_regimes`
- `markov_watch_reason`

For the current long candidate, `BULL_TREND` is the known supportive regime because the Markov gate then returns `REGIME_SUPPORTS_CANDIDATE`.

## Strategy Input Watch

R94 reports:

- `sample_count`
- `win_rate_pct`
- `avg_pnl_pct`
- `total_pnl_pct`
- `best_pnl_pct`
- `worst_pnl_pct`
- `source_recommendation`
- `strategy_inputs_present`
- `strategy_inputs_acceptable_for_review`
- `strategy_input_blockers`

Current strategy inputs are acceptable for review only when the source recommendation remains `ELIGIBLE_FOR_FUTURE_TINY_LIVE` and the strategy row has no blockers.

## Still Not Live Permission

Even if Miro Fish and Markov support are restored, R94 remains non-executable. Restored support only means the candidate may be reconsidered for later review gates.

R94 does not bypass:

- R84 preflight
- R87 live-env boundary
- missing R89 review records
- human approval requirements
- dry-run/no-order guarantees

## Surfaces

API:

```text
GET /live-arming/candidate-revalidation-watch
POST /live-arming/candidate-revalidation-watch/report
```

CLI:

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward candidate-revalidation-watch
```

Optional scheduler task:

```text
candidate_revalidation_watch
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
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward candidate-revalidation-watch | sed -n '1,340p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward live-arming-preflight | sed -n '1,220p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward source-chain-repair | sed -n '1,260p'
```

API smoke checks are only appropriate if the local service is already running. R94 does not require a service restart for local code validation.

## Next Phase Recommendation

If support is not restored, use:

```text
R95 Markov Support Watch Scheduler / Candidate Revalidation Loop
```

If support is restored, use:

```text
R95 Human Confirmation Record Trial, still non-executable
```

Human confirmation should only proceed after support is restored and still must preserve R84/R87/R89 boundaries and all no-order guarantees.
