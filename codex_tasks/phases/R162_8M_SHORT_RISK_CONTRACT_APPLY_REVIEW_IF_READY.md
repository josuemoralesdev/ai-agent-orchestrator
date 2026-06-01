# R162 8m Short Risk Contract Apply Review If Ready

## Phase

`R162`

## Branch

`r162-8m-short-risk-contract-apply-review-if-ready`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R161 drafts the missing risk-contract preview for `BTCUSDT|8m|short|ladder_close_50_618`. R162 should review whether that draft can be applied in a later config-write phase, while defaulting to blocked unless evidence, funding, operator review, and exact future confirmation are present.

## Assigned Agents

- builder: implement only the apply-review packet or doc surface
- index: verify this does not duplicate R161, R160, R159, R158, or existing risk-contract validation
- qa: validate preview-only behavior and safety flags
- security: enforce no live trading, no Binance calls, no payloads, and no unauthorized config writes

## Main Objective

Create an apply-review readiness packet for the R161 8m short risk-contract draft. The default outcome must be blocked unless all readiness gates and explicit operator confirmation are present.

## Capability Scan

Inspect:

- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R161_8M_SHORT_RISK_CONTRACT_DRAFT_PREVIEW.md`
- `src/app/hammer_radar/operator/short_risk_contract_draft_preview.py`
- `src/app/hammer_radar/operator/fundless_short_dry_run_packet.py`
- `src/app/hammer_radar/operator/fundless_short_tiny_live_readiness_rehearsal.py`
- `src/app/hammer_radar/operator/short_evidence_recheck_packet.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract.py`
- `configs/hammer_radar/lane_controls.json`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- related tests under `tests/hammer_radar/`

## Reuse / Extend / Create Decision

- Existing capability reused: R161 draft preview, R160 dry-run packet, R158 evidence recheck, existing tiny-live risk-contract config shape.
- Existing capability extended: inspect CLI only if a new apply-review command is required.
- New capability created: only a review surface if existing R161 output cannot express the apply readiness.
- Why new code is necessary: R162 may need to compose readiness gates into a decision about whether a later config-write phase can be considered.
- Why this does not duplicate prior work: R161 drafts; R162 reviews whether applying the draft is even allowed to be proposed.

## Required Defaults

- no lane mode change
- no live execution
- no order
- no Binance call
- no signed request
- no order payload
- no protective payload
- no env mutation
- no global live flag mutation
- no config write by default
- no config write unless a future explicit operator confirmation and tests authorize exactly that action

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile src/app/hammer_radar/operator/inspect.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_short_risk_contract_draft_preview.py
```

Add focused R162 tests if R162 creates a module.

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order, test-order, protective, account, or balance endpoints.
- Do not create executable exchange payloads.
- Do not create signed request material.
- Do not modify env flags.
- Do not change lane modes.
- Do not write `configs/hammer_radar/tiny_live_risk_contracts.json` unless a future phase explicitly authorizes a config write with exact confirmation and tests.
- Do not expose secrets.
- Preserve paper/live separation and kill-switch discipline.

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
