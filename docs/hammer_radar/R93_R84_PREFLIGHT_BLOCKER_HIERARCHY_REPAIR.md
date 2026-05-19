# R93 R84 Preflight Blocker Hierarchy Repair

R93 repairs the R84 live arming preflight output so operator diagnostics distinguish direct strategy-quality blockers from risk, funding, and approval checks that were not truly evaluated because R84 did not select a supported candidate.

R93 is diagnostic and preflight-output repair only. It does not place orders, sign payloads, create executable exchange payloads, call Binance, check balances, modify env files, restart services, disable the kill switch, or enable live execution.

## Why R93 Exists

R92 confirmed the current exact candidate is present but not supported for live arming:

- `candidate_id=normal|BTCUSDT|13m|long|ladder_close_50_618`
- `final_quality_status=MIRO_FISH_OPERATOR_REVIEW_ONLY`
- `final_quality_score=92`
- `markov_regime=LOW_VOLATILITY`
- `markov_gate_status=REGIME_NEUTRAL_OR_INSUFFICIENT_DATA`
- `final_preflight_status=BLOCKED_BY_STRATEGY_QUALITY`

R92 also found that R84 reported risk/funding blockers as if they were direct blockers even though no supported Miro Fish candidate became `top_candidate_preflight`. Those risk/funding blockers were cascading interpretation artifacts, not direct evaluations of the exact candidate by R84.

R84.1 risk contract and funding continuity can still be valid independently for the exact known candidate. R93 makes that independent continuity visible without letting R84 use it unless R84 first selects the candidate.

## New Blocker Hierarchy

When no supported Miro Fish candidate is selected, R84 now emits `preflight_blocker_hierarchy`:

- `hierarchy_status=PREFLIGHT_BLOCKER_HIERARCHY_REPAIRED`
- `primary_blockers=["no_supported_miro_fish_candidate"]`
- `secondary_blockers` for risk, funding, and operator approval checks that were not evaluated
- `cascading_blockers` for legacy risk/funding names that explain older downstream diagnostics
- `not_evaluated` booleans for `risk_contract`, `funding_config`, and `operator_approval`
- `independent_continuity` for valid R84.1 risk/funding continuity that was not selected by R84

The top-candidate null path now reports:

- `risk_contract_status=RISK_CONTRACT_NOT_EVALUATED_NO_CANDIDATE`
- `funding_status=FUNDING_NOT_EVALUATED_NO_CANDIDATE`
- `operator_approval_status=OPERATOR_APPROVAL_NOT_EVALUATED_NO_CANDIDATE`
- `final_preflight_status=BLOCKED_BY_STRATEGY_QUALITY`

Supported-candidate behavior remains unchanged: R84 still evaluates risk, funding, live-env locks, and missing operator approval normally after a candidate is selected.

## R90/R91/R92 Readability

R90 surfaces the R84 hierarchy in the readiness snapshot and exposes primary, secondary, and cascading preflight blockers separately in `blocker_summary`.

R91 consumes the hierarchy for `current_preflight_diagnostic.primary_root_blocker` and reports cascading risk/funding blockers without treating them as direct root causes.

R92 consumes the hierarchy instead of re-inferring all blocker semantics manually. When the hierarchy is present, R92 recommends `R94 Current Candidate Revalidation + Markov Support Watch` rather than another hierarchy repair phase.

## Unchanged Gates

R93 does not change:

- Miro Fish thresholds or support criteria
- Markov regime thresholds or gate criteria
- candidate selection thresholds
- R84.1 risk contract values
- funding config values
- live env toggles
- execution behavior
- R87 boundary behavior
- R89 review-record requirements

## Safety Guarantees

R93 keeps:

- `live_execution_enabled=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `network_allowed=false`
- `secrets_shown=false`
- no executable ticket, packet, checklist, or readiness snapshot conversion

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
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward live-arming-preflight | sed -n '1,260p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward readiness-snapshot | sed -n '1,260p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward source-chain-repair | sed -n '1,260p'
```

API smoke checks are only appropriate if the local service is already running. R93 does not require a service restart.

## Next Phase Recommendation

Use `R94 Current Candidate Revalidation + Markov Support Watch` while the source chain remains review-only under current Markov and Miro Fish results.

Use `R94 Human Confirmation Record Trial` only if a later source-chain snapshot becomes clean, R84 selects a supported candidate, R87 remains intact, and missing R89 record requirements are addressed without changing execution readiness.
