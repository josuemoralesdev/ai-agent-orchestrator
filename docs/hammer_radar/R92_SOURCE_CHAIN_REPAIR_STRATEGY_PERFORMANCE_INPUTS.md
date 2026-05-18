# R92 Source Chain Repair For Strategy Performance Inputs

## Purpose

R92 diagnoses why the BTCUSDT 13m tiny-live candidate moved from current support into operator-review-only status, and it separates current evidence from advisory interpretation.

R92 does not place orders, sign payloads, create executable exchange payloads, call Binance, check balances, modify env files, restart services, disable the kill switch, or enable live execution.

## Why R92 Follows R91

R91 showed that the candidate is present in the current source chain but now reports:

- `final_quality_status=MIRO_FISH_OPERATOR_REVIEW_ONLY`
- `final_quality_score=92`
- `source_recommendation=ELIGIBLE_FOR_FUTURE_TINY_LIVE`
- `markov_regime=LOW_VOLATILITY`
- `markov_gate_status=REGIME_NEUTRAL_OR_INSUFFICIENT_DATA`
- `current_preflight_status=BLOCKED_BY_STRATEGY_QUALITY`
- `source_warning_classification=STRATEGY_PERFORMANCE_DRIFT`

R92 explains that drift without forcing support or changing readiness.

## Candidate And Current Hashes

Candidate:

```text
normal|BTCUSDT|13m|long|ladder_close_50_618
```

Current risk contract hash:

```text
3926f7155cbe5551a0781178a7ab79fc3e2dbd2ca8dd82c4914153a47a253c1f
```

Current packet hash:

```text
c953963a7cd65884fb2124c5f4924ca092ad76caa99699a72593cd340d8273ab
```

Hashes are surfaced from the canonical R85/R88/R89 dry-run chain. R92 does not hardcode stale hash values or treat hash consistency as live permission.

## Diagnostics

R92 reads:

- R83 Miro Fish quality gate
- R82 Markov regime gate
- R84 live arming preflight
- R84.1 tiny-live risk contract
- R90 readiness snapshot
- R91 source warning review
- strategy performance live-eligibility matrix

The diagnostic payload includes:

- current Miro Fish status, score, votes, and downgrade reasons
- current Markov regime, gate status, prior documented regime, and likely effect
- current strategy performance inputs and missing fields
- R84 preflight selection status and cascading blockers
- R84.1 risk contract continuity
- R85/R88/R89 hash-chain continuity
- Operator/Architect Seat advisory review

## Council Vs Operator/Architect Seat

The council remains evidence-based. The Operator/Architect Seat is advisory only.

It cannot:

- override Markov
- override Miro Fish
- bypass R87
- bypass missing R89 review records
- make a ticket executable
- create payloads
- create execution permission

It can request revalidation, source mapping repair, or a blocker hierarchy repair.

## Drift Interpretation

When Markov is `LOW_VOLATILITY` and the gate is `REGIME_NEUTRAL_OR_INSUFFICIENT_DATA`, R92 treats the Markov change from prior documented `BULL_TREND` as current regime drift.

When Miro Fish is `MIRO_FISH_OPERATOR_REVIEW_ONLY`, R92 keeps the candidate review-only even if the strategy performance recommendation remains `ELIGIBLE_FOR_FUTURE_TINY_LIVE`.

When R84 preflight has no supported Miro Fish candidate, risk/funding blockers may be reported as secondary/cascading because the candidate never becomes the selected `top_candidate_preflight`. R92 recommends a future R84 blocker hierarchy repair when that is present.

## API

```text
GET /live-arming/source-chain-repair
POST /live-arming/source-chain-repair/report
```

The report endpoint defaults to dry-run/no-write. `dry_run=false` and `write=true` may write local JSON only:

```text
logs/hammer_radar_forward/source_chain_repair_report.json
```

## CLI

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward source-chain-repair
```

## Safety Guarantee

Every R92 payload keeps:

```text
review_only=true
executable=false
env_modified=false
order_type=not_created
order_payload_created=false
execution_attempted=false
network_allowed=false
secrets_shown=false
live_execution_enabled=false
allow_live_orders=false
global_kill_switch=true
order_placed=false
real_order_placed=false
```

## Smoke Commands

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward source-chain-repair | sed -n '1,340p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward source-warning-review | sed -n '1,260p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward readiness-snapshot | sed -n '1,220p'
```

## Next Phase Recommendation

Choose R93 from the actual R92 result:

- `R93 Current Candidate Revalidation + Markov/Miro Fish Threshold Review` when current market/regime drift is the primary cause.
- `R93 R84 Preflight Blocker Hierarchy Repair` when R84 mixes primary strategy-quality blockers with secondary risk/funding blockers that were not actually evaluated because no candidate was selected.

Do not treat live execution as the next step.
