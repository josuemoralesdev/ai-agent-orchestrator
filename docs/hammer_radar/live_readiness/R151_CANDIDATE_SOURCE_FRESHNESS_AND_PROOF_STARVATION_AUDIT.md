# R151 Candidate Source Freshness and Proof Starvation Audit

Phase: R151

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## Why R151 Follows R150

R150 made the 12h fresh proof watcher bounded and observable. The post-R150 run completed all 720 iterations with `FRESH_CANDIDATE_WATCH_TIMEOUT`, `paper_proof_captured=false`, and `next_operator_move=WAIT_FOR_FRESH_CANDIDATE`.

R151 answers the next question: whether that timeout means the market was quiet, source feeds were stale or stopped, target-lane signals existed but were stale or mismatched, the watcher bounded scan missed candidates, or the paper proof capture path was blocked after an eligible signal.

R151 is diagnostic only. It does not start the watcher, restart services, call Binance, create payloads, mutate lanes, widen lanes, add shorts, bypass freshness, or create paper proof.

## Audit Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  candidate-source-freshness-audit \
  --latest-signals 1000 \
  --latest-scans 2000
```

Record audit:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  candidate-source-freshness-audit \
  --latest-signals 1000 \
  --latest-scans 2000 \
  --record-audit \
  --confirm-audit "I CONFIRM CANDIDATE SOURCE AUDIT RECORDING ONLY; NO ORDER; NO BINANCE CALL."
```

The audit ledger is append-only:

```text
logs/hammer_radar_forward/candidate_source_freshness_audits.ndjson
```

## Source Surfaces

R151 reads:

- `fresh_candidate_paper_proof_watch_heartbeats.ndjson`
- `fresh_candidate_paper_proof_capture_loop.ndjson`
- `signals.ndjson`
- `multi_symbol_paper_scans.ndjson`
- `paper_refresh_runs.ndjson`
- `market_intelligence_snapshots.ndjson`
- `configs/hammer_radar/lane_controls.json`

It reuses R145 read-path normalization so missing `entry_mode` BTCUSDT 13m/44m long records can be evaluated against `BTCUSDT|13m|long|ladder_close_50_618` and `BTCUSDT|44m|long|ladder_close_50_618` without mutating source logs.

## Starvation Classifications

- `SOURCE_FEED_STALE_OR_STOPPED`: source ledgers did not show live scanner/market input during or near the watch window.
- `NO_TARGET_LANE_SIGNALS_DURING_WINDOW`: sources were live, but no BTCUSDT 13m/44m long target-lane signal appeared.
- `TARGET_LANE_SIGNALS_ALL_STALE`: target-lane candidates existed but exceeded lane freshness.
- `TARGET_TIMEFRAME_PRESENT_BUT_WRONG_DIRECTION`: target timeframes appeared, but not long.
- `TARGET_DIRECTION_PRESENT_BUT_WRONG_TIMEFRAME`: BTCUSDT long candidates appeared on non-target timeframes.
- `ENTRY_MODE_OR_LANE_KEY_MISMATCH`: target symbol/timeframe/direction existed but lane key or entry mode did not match after normalization.
- `WATCH_SCAN_WINDOW_TOO_NARROW`: broader audit tail found target-lane rows outside the watcher bounded tail.
- `PAPER_CAPTURE_BLOCKED_AFTER_ELIGIBLE_SIGNAL`: an eligible signal reached capture eligibility, but R140/R129 did not record paper proof.
- `WATCHER_HEALTHY_MARKET_QUIET`: watcher and sources look healthy, but the market did not produce target-lane opportunity.
- `UNKNOWN_NEEDS_MANUAL_REVIEW`: ledgers do not identify one dominant cause.

## Next Moves

If source feed is stale or stopped, the operator should manually check paper refresh/radar services. Codex should not restart services.

If target-lane signals were all stale, continue or schedule a bounded R150 watcher and wait for a fresh target-lane candidate.

If wrong direction dominates, use a future R152 short-lane paper-only betrayal/short candidate audit. Do not enable live shorts.

If no target-lane signals appeared while sources were live, use R152 Candidate Opportunity Expansion Audit to compare 4m/8m/13m/44m/88m long/short paper opportunity distribution. Do not widen live lanes yet.

If the scan window was too narrow, increase `--latest-signals` on the watcher while keeping freshness, heartbeat, and iteration guards intact.

If paper capture was blocked after eligibility, fix the R140/R129 blocker before retrying.

## Safety Boundary

R151 preserves:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `secrets_shown=false`
- no Binance order/test/protective/private calls
- no signed request material
- no env mutation
- no lane config mutation
- no global live flag mutation
- no kill-switch disable
- no fake paper proof
- no lane widening
- no short enablement

`tiny_live` lane mode remains operator intent only and remains blocked behind global/protective/live gates.
