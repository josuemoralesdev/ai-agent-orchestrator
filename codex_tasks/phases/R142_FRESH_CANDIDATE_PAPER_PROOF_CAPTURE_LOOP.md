# R142 Fresh Candidate Paper Proof Capture Loop

## Phase

`R142`

## Branch

`r142-fresh-candidate-paper-proof-capture-loop`

## Phase Classification

- Primary classification: WIRING / INTEGRATION
- Secondary classification(s): DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## Reason

R141 can correctly decide `WAIT_FOR_FRESH_CANDIDATE` after R140 when no fresh eligible routed candidate exists. R142 should implement a safe bounded watch loop that waits for a fresh router/R129 eligible decision and captures paper proof through the existing R129/R140 safe path.

## Main Objective

Implement a bounded, operator-started, non-executing watch loop that polls fresh router and R129 eligibility, stops safely, and records before/after paper-proof state when eligible.

## Required Behavior

- No real orders.
- No Binance calls.
- No Binance test-order calls.
- No protective order calls.
- No executable order payloads.
- No protective payloads.
- No signed requests.
- No env mutation.
- No lane config mutation.
- No global live flag changes.
- No kill-switch disabling.
- Poll R123 fresh router status.
- Poll R129 autonomous paper lane executor integration preview.
- When eligible, capture paper proof only through the existing R129/R140 safe confirmation path.
- Stop after proof, timeout, safety issue, router error, lane config drift, or operator stop.
- Produce before/after proof state and an append-only diagnostic ledger.

## Expected Files

- `src/app/hammer_radar/operator/fresh_candidate_paper_proof_capture_loop.py`
- `tests/hammer_radar/test_fresh_candidate_paper_proof_capture_loop.py`
- `docs/hammer_radar/live_readiness/R142_FRESH_CANDIDATE_PAPER_PROOF_CAPTURE_LOOP.md`

## CLI

Proposed command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fresh-candidate-paper-proof-capture-loop \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --interval-seconds 60 \
  --max-runtime-minutes 180
```

Default should be preview/plan only unless an exact R142 watch-loop confirmation phrase is supplied.

## Tests Required

- Preview does not loop or write.
- Wrong confirmation rejects.
- Exact confirmation starts only the bounded safe loop.
- Polls router and R129 previews only.
- Captures paper proof only through R129/R140 safe path when eligible.
- Stops on proof captured.
- Stops on timeout.
- Stops on safety violation.
- Stops on router error.
- Stops on lane config drift.
- Stop command/file/flag is honored if implemented.
- Before/after proof state is included.
- No Binance/order/payload/network/env/config mutation.
- Safety flags stay false except paper/live separation true.

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order or test-order endpoints.
- Do not call protective order endpoints.
- Do not create executable or protective payloads.
- Do not create signed request material.
- Do not mutate env files or lane config.
- Do not disable the global kill switch.
- Do not install/start services.
- Do not run `sudo`.
- Do not commit, merge, tag, push, or deploy.
