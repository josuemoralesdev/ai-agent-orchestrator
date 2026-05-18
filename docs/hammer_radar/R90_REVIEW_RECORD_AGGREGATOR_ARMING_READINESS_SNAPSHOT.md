# R90 Review Record Aggregator + Arming Readiness Snapshot

## Purpose

R90 adds one deterministic, read-only readiness snapshot across the R83-R89.1 review chain for the BTCUSDT tiny-live candidate.

It answers whether review records exist, whether R85/R88/R89 hashes agree, whether R87 still blocks live arming, what source warnings remain, and what human actions are still required.

R90 does not place orders, sign payloads, create executable exchange payloads, call Binance, check balances, modify env files, restart services, disable the kill switch, or enable live execution.

## Why R90 Follows R89.1

R89.1 made R88/R89 API responses reliable when malformed local candle archive lines exist and clarified that hash values are generated from canonical source snapshots. R90 consumes those safer surfaces and aggregates them into a single operator view.

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

These hashes are not hardcoded into R90. They are surfaced from the canonical R85/R88/R89 dry-run chain.

## Aggregation Inputs

R90 reads:

- R83 Miro Fish quality gate
- R84 live arming preflight
- R84.1 tiny-live risk contract
- R85 tiny-live ticket builder and ticket records
- R86 live-env checklist status
- R87 live-env boundary review
- R88 final human review packet
- R89 human confirmation records status

## Hash-Chain Consistency

R90 compares:

- R85 `risk_contract_hash`
- R88 `risk_contract_hash`
- R89 `risk_contract_hash`
- R88 `packet_hash`
- R89 `packet_hash`

The snapshot returns `hash_chain_consistent=true` only when all current risk hashes agree and R88/R89 packet hashes agree.

## Source Warnings

If R88 reports `REVIEW_PACKET_BLOCKED_BY_SOURCE_WARNINGS`, R90 returns:

```text
source_chain_status=SOURCE_CHAIN_WARNINGS_PRESENT
source_warning_review_required=true
```

Source warnings remain blockers. They do not become execution permission.

## Snapshot Statuses

Possible statuses include:

- `ARMING_SNAPSHOT_REVIEW_ONLY`
- `ARMING_SNAPSHOT_BLOCKED_BY_SOURCE_WARNINGS`
- `ARMING_SNAPSHOT_BLOCKED_BY_MISSING_REVIEW_RECORDS`
- `ARMING_SNAPSHOT_BLOCKED_BY_LIVE_ENV_BOUNDARY`
- `ARMING_SNAPSHOT_BLOCKED_BY_HASH_MISMATCH`
- `ARMING_SNAPSHOT_RECORDS_PARTIAL`
- `ARMING_SNAPSHOT_RECORDS_COMPLETE_FOR_REVIEW`
- `ARMING_SNAPSHOT_NON_EXECUTABLE_ONLY`

## Readiness Classes

Possible readiness classes include:

- `NOT_READY_FOR_LIVE_ARMING`
- `READY_FOR_HUMAN_RECORD_COMPLETION`
- `REVIEW_RECORDS_COMPLETE_BUT_ENV_LOCKED`
- `SOURCE_CHAIN_NEEDS_REVIEW`
- `HASH_CHAIN_INVALID`
- `NON_EXECUTABLE_REVIEW_READY`

Current expected local state is blocked by missing human confirmation records, R87 live-env boundary, and possibly source warnings.

## API

```text
GET /live-arming/readiness-snapshot
POST /live-arming/readiness-snapshot/report
```

The report endpoint defaults to dry-run/no-write. `dry_run=false` and `write=true` may write local JSON only:

```text
logs/hammer_radar_forward/review_record_arming_snapshot.json
```

## CLI

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward readiness-snapshot
```

## Safety Guarantee

Every R90 payload keeps:

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
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward readiness-snapshot | sed -n '1,320p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward human-confirmations | sed -n '1,220p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward final-review-packet | sed -n '1,220p'
```

## Next Phase Recommendation

Choose R91 from the actual R90 result:

- If source warnings remain primary, do `R91 Source Warning Review + Candidate Support Rehydration`.
- If source chain is clean and records are missing, do `R91 Human Confirmation Record Write Trial`.

Do not treat live execution as the next step.

R91 adds Source Warning Review + Candidate Support Rehydration to explain source-chain support gaps before any human confirmation write trial.

R92 follows when R91 classifies the gap as strategy performance drift. It diagnoses Markov/Miro Fish/preflight interpretation and keeps any Operator/Architect Seat recommendation advisory only.
