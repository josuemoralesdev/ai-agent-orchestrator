# Phase

`R158 Short Evidence Recheck And Promotion Readiness Packet`

## Branch

`r158-short-evidence-recheck-promotion-readiness-packet`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R156 found promising historical paper evidence for `BTCUSDT|8m|short|ladder_close_50_618`, but blocked promotion discussion because fresh short candidate evidence was missing. R157 added a bounded paper-only capture loop for that lane.

R158 should run only after R157 capture records exist. It must recheck whether the fresh evidence threshold is now met and produce a promotion-readiness packet only.

## Assigned Agents

- builder: implement the packet surface
- index: verify duplicate risk and update phase index
- qa: validate packet output and safety flags
- security: verify no live execution, no Binance calls, no lane-mode changes

## Main Objective

Build a read-only R158 recheck packet for `BTCUSDT|8m|short|ladder_close_50_618` that composes:

- R157 short paper evidence capture records
- R156 short strategy packet output
- R155 full-spectrum betrayal short review output
- lane control read-only state

The packet may say promotion-readiness review is possible, but it must not apply any lane change.

## Capability Scan

Inspect:

- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R156_SHORT_STRATEGY_PACKET_8M_SHORT.md`
- `docs/hammer_radar/live_readiness/R157_SHORT_PAPER_EVIDENCE_CAPTURE_LOOP.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `src/app/hammer_radar/operator/short_strategy_packet.py`
- `src/app/hammer_radar/operator/full_spectrum_betrayal_short_review.py`
- `src/app/hammer_radar/operator/short_paper_evidence_capture_loop.py`
- `src/app/hammer_radar/operator/lane_control.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/test_short_strategy_packet.py`
- `tests/hammer_radar/test_full_spectrum_betrayal_short_review.py`
- `tests/hammer_radar/test_short_paper_evidence_capture_loop.py`
- `configs/hammer_radar/lane_controls.json`
- `logs/hammer_radar_forward/short_paper_evidence_capture.ndjson`
- existing CLI command names
- existing scheduler tasks

## Reuse / Extend / Create Decision

- Existing capability reused: R155, R156, R157, lane controls
- Existing capability extended: inspect CLI with a narrow R158 packet mode
- New capability created: one R158 promotion-readiness packet module if no existing module cleanly owns the composition
- Why new code is necessary: R158 composes evidence across R155/R156/R157 and needs its own threshold and packet output
- Why this does not duplicate prior work: it does not reimplement strategy scoring or capture logic; it only summarizes existing evidence into a next-review packet

## Required Safety Constraints

- Do not place orders.
- Do not create executable Binance order payloads.
- Do not create protective order payloads.
- Do not call Binance.
- Do not call account/order/private endpoints.
- Do not sign requests.
- Do not print secrets.
- Do not mutate env files.
- Do not mutate global live flags.
- Do not mutate `configs/hammer_radar/lane_controls.json`.
- Do not set any lane to `tiny_live`.
- Do not set any short lane to `tiny_live`.
- Do not change existing tiny-live lane modes.
- Do not disable the kill switch.
- Do not mark global gate ready.
- Do not bypass freshness.
- Do not create fake proof.
- Do not commit, merge, tag, push, deploy, run `sudo`, or restart services.

## Expected Behavior

R158 should:

- load R157 capture records
- compute fresh captured sample count for the target short lane
- re-run or compose R156 short strategy packet
- re-run or compose R155 full-spectrum betrayal short review
- decide whether the 8m short lane meets the fresh evidence threshold
- emit a promotion-readiness packet only when thresholds are satisfied
- otherwise report exact blockers

R158 must not:

- apply a lane mode change
- output lane mode apply commands
- output live execution commands
- imply tiny-live authorization
- clear global or protective gates

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/<r158_module>.py \
  src/app/hammer_radar/operator/inspect.py
```

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/<r158_test_file>.py \
  tests/hammer_radar/test_short_strategy_packet.py \
  tests/hammer_radar/test_full_spectrum_betrayal_short_review.py \
  tests/hammer_radar/test_short_paper_evidence_capture_loop.py
```

## Final Report Format

Report:

- Branch:
- Phase Classification:
- Capability scan summary:
- Reuse / Extend / Create decision:
- Duplicate risk report:
- Files created:
- Files modified:
- Tests or checks run:
- Smoke checks run, if any:
- Runtime behavior changed:
- Safety result:
- Blockers, if any:
- Exact manual commands needed, if any:
