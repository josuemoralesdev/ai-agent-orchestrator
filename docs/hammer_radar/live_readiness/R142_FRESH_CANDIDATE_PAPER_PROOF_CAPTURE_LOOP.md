# R142 Fresh Candidate Paper Proof Capture Loop

R142 adds a bounded, operator-started watcher loop for fresh autonomous lane candidates. It exists because R141 can correctly end at `WAIT_FOR_FRESH_CANDIDATE`: no fresh routed candidate, stale paper evidence only, and a plan-only `SAFE_WATCH_ONLY` handoff.

R142 implements that handoff without changing live readiness authority. It watches only, collects read-only snapshots, and attempts paper proof only through the existing R140 safe clearing executor. R140 then delegates paper evidence to R129 with the R129 paper-only confirmation phrase.

## Watched Lanes

Default primary lane:

```text
BTCUSDT|13m|long|ladder_close_50_618
```

Recommended secondary lane:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

Use `--watch-all-recommended-lanes` to watch both. If no lane is specified and that flag is not present, R142 defaults to the 13m lane for compatibility with the existing R138/R140/R141 lane default.

## What R142 Does

- Previews the watcher plan by default.
- Runs only after the exact R142 confirmation phrase.
- Polls fresh router, R128 scheduler preview, R129 paper integration preview, R141 recheck, and R138 burn-down summary.
- Attempts capture only when a lane has a fresh routed candidate and eligible paper decisions.
- Stops after proof capture, timeout, safety stop, or diagnostic error.
- Optionally records an append-only watcher ledger.

## What R142 Does Not Do

- No orders.
- No Binance order, test-order, protective, account, balance, or private endpoint calls.
- No executable order payloads.
- No protective payloads.
- No signed request material.
- No env or lane config mutation.
- No live flag changes.
- No kill-switch changes.
- No service install/start behavior.
- No direct proof creation by R142.

## Confirmation Phrase

The watch loop requires this exact phrase:

```text
I CONFIRM FRESH CANDIDATE PAPER PROOF WATCH ONLY; NO ORDER; NO BINANCE CALL.
```

This authorizes only a bounded watch loop, read-only checks, and safe paper proof capture through R140/R129 when eligible. It does not authorize live execution or exchange access.

## Loop Limits

- `--max-iterations`: default `5`, bounded to `1..180`.
- `--sleep-seconds`: default `60`, bounded to `10..300`.
- Codex smoke checks should use at most one iteration.
- Longer watches are operator-run, not service-installed by R142.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fresh-candidate-paper-proof-capture-loop \
  --watch-all-recommended-lanes
```

Short safe loop:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fresh-candidate-paper-proof-capture-loop \
  --watch-all-recommended-lanes \
  --max-iterations 2 \
  --sleep-seconds 10 \
  --run-watch-loop \
  --record-watch \
  --confirm-watch-loop "I CONFIRM FRESH CANDIDATE PAPER PROOF WATCH ONLY; NO ORDER; NO BINANCE CALL."
```

Longer operator watch:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fresh-candidate-paper-proof-capture-loop \
  --watch-all-recommended-lanes \
  --max-iterations 30 \
  --sleep-seconds 60 \
  --run-watch-loop \
  --record-watch \
  --confirm-watch-loop "I CONFIRM FRESH CANDIDATE PAPER PROOF WATCH ONLY; NO ORDER; NO BINANCE CALL."
```

## Ledger

R142 writes only when `--record-watch` is supplied on a confirmed loop:

```text
logs/hammer_radar_forward/fresh_candidate_paper_proof_capture_loop.ndjson
```

Each record includes watched lanes, loop limits, iteration summaries, final lane statuses, capture evidence IDs if any, next operator move, safety fields, and source surfaces used.

## Stop Conditions

- Paper proof captured through R140/R129.
- Max iterations reached.
- Safety field violation.
- Diagnostic exception.
- Invalid confirmation before loop start.

After capture, the next move is a post-capture recheck, not live execution. R143 should compare before/after proof state and re-evaluate tiny-live authorization readiness without orders or Binance calls.
