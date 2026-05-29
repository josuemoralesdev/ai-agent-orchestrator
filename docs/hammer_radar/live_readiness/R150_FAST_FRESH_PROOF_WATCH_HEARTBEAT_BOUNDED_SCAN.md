# R150 Fast Fresh Proof Watch Heartbeat Bounded Scan

Phase: R150

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## Why R150 Exists

After R149 prepared a safe post-`tiny_live` fresh-proof watch command, the human operator ran a 720-iteration watcher. The process ran for roughly two hours at high CPU, wrote no new final watcher ledger record, and left the latest `fresh_candidate_paper_proof_capture_loop.ndjson` entry pointing at the previous 60-iteration timeout.

R150 makes long watch windows observable and bounded. It keeps the R142 proof-capture surface, but adds a fast watch path with heartbeat records, bounded signal reads, and an iteration timeout guard.

## Heartbeat Ledger

The heartbeat ledger is append-only:

```text
logs/hammer_radar_forward/fresh_candidate_paper_proof_watch_heartbeats.ndjson
```

Each watch loop writes progress records with:

- `WATCH_ITERATION_STARTED`
- `WATCH_ITERATION_COMPLETED`
- `WATCH_ITERATION_TIMEOUT`
- `WATCH_CAPTURED_PROOF`
- `WATCH_EXITED`

The heartbeat includes the watch id, iteration number, elapsed seconds, watched lanes, candidate counts, fresh/stale normalized counts, paper-proof capture state, next operator move, and safety flags.

## Bounded Scan And Guard

R150 adds bounded watcher options:

```text
--latest-signals 250
--latest-scans 500
--iteration-timeout-seconds 30
--heartbeat-every 1
--heartbeat-ledger-path <optional path>
```

Defaults are intentionally small enough for long runs:

- latest signals default: `250`, capped at `5000`
- latest scans default: `500`, capped at `10000`
- iteration timeout default: `30` seconds
- heartbeat every default: `1`

The watcher now uses recent NDJSON tail reads for signal candidates instead of loading the full `signals.ndjson` archive for each lane.

## Fast Watch Path

The watch-loop snapshot uses the R149/R147 fast global-gate sentinel and provided eligibility matrix data. It does not call the full first-live activation gate, live preflight, R141 post-clearing recheck, R138 burn-down, Markov/Miro archive, or candle archive path during routine watch iterations.

Paper proof is still recorded only through the existing safe R140/R129 path when an actually eligible fresh candidate is detected. R150 does not force proof and does not make stale candidates fresh.

## Safe 12h Command

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fresh-candidate-paper-proof-capture-loop \
  --watch-all-recommended-lanes \
  --max-iterations 720 \
  --sleep-seconds 60 \
  --latest-signals 250 \
  --iteration-timeout-seconds 30 \
  --heartbeat-every 1 \
  --run-watch-loop \
  --record-watch \
  --confirm-watch-loop "I CONFIRM FRESH CANDIDATE PAPER PROOF WATCH ONLY; NO ORDER; NO BINANCE CALL."
```

The CLI emits compact progress lines to stderr while preserving JSON on stdout.

## Safety Boundary

R150 does not place orders, create executable Binance order payloads, create protective payloads, call Binance order/test-order/protective endpoints, call private account/order endpoints, send signed requests, mutate env files, mutate global live flags, disable the kill switch, bypass R106/global gates for live execution, bypass protective policy, bypass freshness, create fake paper proof, widen lanes, or add shorts.

`tiny_live` lane mode remains intent only. Live execution still requires a later explicitly authorized phase.

## After Captured Proof

After the watcher captures fresh paper proof, run the R151 recheck phase. It should recheck tiny-live gates, live safety, Binance read-only/funding evidence, and prepare a final tiny-live readiness packet without live execution.
