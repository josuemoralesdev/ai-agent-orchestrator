# R89.1 Human Confirmation API + Hash Chain Hotfix

## Purpose

R89.1 fixes R88/R89 reliability after local smoke showed plaintext HTTP 500 responses from malformed local candle archive JSONL lines.

This is a hotfix only. It does not place orders, create signed payloads, create executable exchange payloads, call Binance, check balances, modify env files, restart services, disable the kill switch, or enable live execution.

## Why It Exists

Malformed local candle archive lines previously raised `json.decoder.JSONDecodeError` inside `betrayal_candle_archive._read_jsonl()`. That exception could bubble through:

```text
candle archive -> Miro Fish -> live arming preflight -> R85 ticket -> R88 packet -> R89 confirmations
```

The result was non-JSON HTTP 500 output for dry-run API calls that should always be safe operator review surfaces.

## JSONL Tolerance

R89.1 changes local candle archive JSONL reading to:

- skip malformed JSON lines
- skip non-object JSON lines
- keep valid candle lines
- avoid deleting or rewriting archive files
- avoid fabricating candles
- expose `archive_integrity_warnings` on candle archive status/build payloads

Malformed local data becomes a source warning, not an API crash.

## API JSON Reliability

The dry-run routes must return JSON:

```text
POST /live-arming/review-packet/build
POST /live-arming/human-confirmations/record
GET /live-arming/human-confirmations/status
```

If source warnings exist, R88 may report:

```text
REVIEW_PACKET_BLOCKED_BY_SOURCE_WARNINGS
```

The payload remains review-only and non-executable.

## Hash-Chain Consistency

R89.1 keeps the hash chain generated from canonical source snapshots:

- R85 risk hash = canonical hash of the risk contract snapshot
- R88 risk hash = R85 risk hash
- R89 risk hash = R85/R88 risk hash
- R88 packet hash = canonical hash of the R88 source-chain snapshot
- R89 packet hash = R88 packet hash for the same dry-run source chain

Older docs or previous smoke output may contain stale hash values. Do not force stale values. If the source-chain snapshot or serialization changes legitimately, the current packet hash may change, but R88 and R89 must still agree.

## Safety Guarantees

R89.1 preserves:

```text
review_only=true
executable=false
env_modified=false
order_type=not_created
order_payload_created=false
execution_attempted=false
network_allowed=false
secrets_shown=false
```

R87 remains the live-env boundary and persisted review records are not execution permission.

## Smoke Commands

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward human-confirmations | sed -n '1,220p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward final-review-packet | sed -n '1,220p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward live-env-boundary-review | sed -n '1,160p'
```

After an approved service restart, API smoke should confirm R85/R88/R89 risk hashes agree and R88/R89 packet hashes agree.

## Next Phase Recommendation

R90 should add Review Record Aggregator + Arming Readiness Snapshot. It should remain non-executable unless a later phase explicitly authorizes a separate live execution path with human approval, live-env changes, and safety validation.

R90 now consumes the R89.1 JSON-safe and hash-consistent surfaces to produce one non-executable readiness snapshot.

R91 then diagnoses source-chain support warnings and may surface documented prior review context without treating it as current support.
