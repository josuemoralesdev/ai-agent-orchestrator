# R161 8m Short Risk Contract Draft Preview

## Phase

`R161`

## Branch

`r161-8m-short-risk-contract-draft-preview`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R160 defines the fundless non-executable dry-run packet and operator arming checklist for the future BTCUSDT 8m short tiny-live review path. R161 should draft the target 8m short tiny-live risk contract as a preview artifact only, so the operator can inspect risk limits and protective requirements before any later explicitly approved config mutation phase.

## Assigned Agents

- builder: implement scoped preview code/docs/tests only
- index: verify existing risk-contract and live-readiness surfaces before adding anything
- qa: validate no config write by default and no execution side effects
- security: enforce no live trading, no Binance trading calls, no secrets, no kill-switch bypass

## Main Objective

Create a read-only risk-contract draft preview for:

```text
BTCUSDT|8m|short|ladder_close_50_618
```

The preview must include risk limits, protective order requirements, max daily trades, max daily loss, and kill-switch boundaries. It must not write config by default.

## Capability Scan

Inspect:

- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/lane_controls.json`
- `src/app/hammer_radar/operator/tiny_live_risk_contract.py`
- `src/app/hammer_radar/operator/fundless_short_dry_run_packet.py`
- `src/app/hammer_radar/operator/fundless_short_tiny_live_readiness_rehearsal.py`
- `src/app/hammer_radar/operator/live_arming_preflight.py`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `src/app/hammer_radar/operator/inspect.py`
- related tests under `tests/hammer_radar/`
- live-readiness docs R84/R106/R159/R160

## Reuse / Extend / Create Decision

- Existing capability reused: tiny-live risk-contract config concepts and R160 target-lane packet.
- Existing capability extended: add a preview-only target 8m short risk-contract draft surface.
- New capability created: only if existing risk-contract builder cannot express a draft without writing config.
- Why new code is necessary: the current config has long-lane risk contract data but no reviewed 8m short target-lane contract.
- Why this does not duplicate prior work: R161 must be a draft preview adapter over existing risk-contract semantics, not a new live gate or execution path.

## Duplicate Risk Report

- Similar existing modules: `tiny_live_risk_contract.py`, `live_arming_preflight.py`, `fundless_short_dry_run_packet.py`.
- Similar existing endpoints: live-arming/risk-contract and live preflight surfaces.
- Similar existing CLI commands: `tiny-live-risk-contract`, `fundless-short-dry-run-packet`.
- Similar existing scheduler tasks: risk-contract/preflight scheduler tasks if present.
- Similar existing docs: R84.1, R106, R159, R160.
- Risk: HIGH.
- Mitigation: preview-only by default; no config write, no lane mode change, no live execution, no Binance calls.

## Files Expected

Possible files:

- `src/app/hammer_radar/operator/short_risk_contract_draft_preview.py`
- `tests/hammer_radar/test_short_risk_contract_draft_preview.py`
- `docs/hammer_radar/live_readiness/R161_8M_SHORT_RISK_CONTRACT_DRAFT_PREVIEW.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `src/app/hammer_radar/operator/inspect.py`

Do not edit `.env` files. Do not mutate `configs/hammer_radar/tiny_live_risk_contracts.json` unless a future task adds an explicit confirmation-gated config write path.

## Tests Required

Test:

- preview writes no config
- target lane is BTCUSDT 8m short and remains paper
- risk limits are present
- max daily trades is 1
- max daily loss percent is conservative
- protective orders required
- short-specific stop/TP required
- kill-switch boundary is explicit
- no lane mode change
- no Binance/order/payload/network/env/global mutation
- CLI exists

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/short_risk_contract_draft_preview.py \
  src/app/hammer_radar/operator/inspect.py
```

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_short_risk_contract_draft_preview.py
```

## Safety Constraints

- No config write by default.
- No lane mode change.
- No live execution.
- No Binance order calls.
- No Binance account/balance calls unless a future phase explicitly authorizes a read-only check.
- No executable order payloads.
- No protective order payloads.
- No signed requests.
- No env mutation.
- No kill-switch disable.

## Do Not

- Do not run `sudo`.
- Do not commit, merge, tag, push, deploy, or restart services.
- Do not set any short lane to `tiny_live`.
- Do not change existing tiny-live long lane modes.
- Do not bypass R106/global gates.

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
- Runtime behavior changed:
- Safety result:
- Blockers, if any:
