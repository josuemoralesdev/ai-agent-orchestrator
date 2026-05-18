# R91 Source Warning Review + Candidate Support Rehydration

## Purpose

R91 explains why the current R90 source chain reports that the BTCUSDT tiny-live candidate is not currently supported, and it surfaces any documented prior support as review-only historical context.

R91 does not place orders, sign payloads, create executable exchange payloads, call Binance, check balances, modify env files, restart services, disable the kill switch, or enable live execution.

## Why R91 Follows R90

R90 showed that the review chain is structurally healthy but the source chain needs review:

- `hash_chain_consistent=true`
- R87 boundary remains intact
- R89 review records are missing as expected
- `readiness_class=SOURCE_CHAIN_NEEDS_REVIEW`
- `r83_candidate_not_supported_in_current_source_chain`

R91 focuses on the source support gap, not hash-chain repair.

## Candidate And Hashes

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

## Source Warning Categories

R91 classifies source warnings as one of:

- `ARCHIVE_INTEGRITY_WARNING`
- `CANDIDATE_SUPPORT_MISSING`
- `CURRENT_SOURCE_DATA_INSUFFICIENT`
- `STRATEGY_PERFORMANCE_DRIFT`
- `RUNTIME_DATA_STALE`
- `UNKNOWN_SOURCE_WARNING`

Archive JSONL corruption is no longer assumed when R90 archive integrity warnings are zero.

## Current Vs Rehydrated Support

Current support means the candidate appears in the current R83 Miro Fish output.

Rehydrated context means prior documented review context exists. R91 may show:

- historical candidate id
- historical Miro Fish status
- historical score
- historical source recommendation
- historical Markov regime
- context source

This is labeled `DOCUMENTED_PRIOR_REVIEW_CONTEXT`. It is not current evidence and not live permission.

## Rehydration Statuses

- `REHYDRATION_NOT_NEEDED`
- `REHYDRATION_AVAILABLE_FOR_REVIEW`
- `REHYDRATION_BLOCKED_BY_MISSING_HISTORICAL_CONTEXT`
- `REHYDRATION_REVIEW_ONLY_NOT_CURRENT_SUPPORT`
- `REHYDRATION_REVALIDATION_REQUIRED`

## Safety Guarantee

Every R91 payload keeps:

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

R91 does not bypass R87 boundary, R90 source warnings, or missing R89 records.

## API

```text
GET /live-arming/source-warning-review
POST /live-arming/source-warning-review/report
```

The report endpoint defaults to dry-run/no-write. `dry_run=false` and `write=true` may write local JSON only:

```text
logs/hammer_radar_forward/source_warning_review.json
```

## CLI

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward source-warning-review
```

## Smoke Commands

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward source-warning-review | sed -n '1,320p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward readiness-snapshot | sed -n '1,240p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward final-review-packet | sed -n '1,220p'
```

## Next Phase Recommendation

Choose R92 based on the R91 result:

- `R92 Current Candidate Revalidation from Fresh Runtime Data` when current support is missing or data is insufficient.
- `R92 Source Chain Repair for Strategy Performance Inputs` when performance inputs drifted or disappeared.
- `R92 Archive/Data Hygiene Report` when archive warnings are the source issue.
- `R92 Human Confirmation Write Trial` only if current support is clean.

Do not treat live execution as the next step.

R92 adds Source Chain Repair for Strategy Performance Inputs and an advisory Operator/Architect Seat. The seat may recommend revalidation or source mapping repair, but it cannot override Markov, Miro Fish, R87, missing R89 records, or execution blockers.
