# R229 Tiny Live Risk Contract Preview

## Purpose

Consume the R228 tiny-live 10-of-10 ready packet and prepare a risk-contract preview for the official protected lane:

`BTCUSDT|8m|short|ladder_close_50_618`

This is preview-only. It must not write risk-contract config or create execution authority.

## Inputs

- latest `logs/hammer_radar_forward/tiny_live_10_of_10_ready_packet.ndjson`
- R228 preview output if no recorded packet exists
- read-only local `configs/hammer_radar/tiny_live_risk_contracts.json`
- existing risk-contract draft/apply-review patterns

## Required Behavior

- Verify the R228 packet exists or can be rebuilt from local ledgers.
- Verify `evidence_ready=true`, `fisherman_ready=true`, and `operator_review_ready=true`.
- Keep `risk_contract_config_written=false`.
- Build a proposed risk-contract preview object for operator review only.
- Keep live execution disabled.
- Keep order readiness false.
- Keep lane mode unchanged.

## Non-Negotiable Safety

R229 must not:

- write configs, env files, lane controls, scheduler config, fisherman config, or risk-contract config
- call Binance or any network
- create executable order payloads
- place orders or test orders
- sign trading or readonly requests
- transfer or withdraw
- enable live execution
- disable the kill switch
- set any lane `tiny_live`
- promote any lane, alternate, signal origin, or betrayal path
- infer live readiness from the R228 packet alone

## Validation

- Focused tests for preview-only behavior.
- Compile check for any new module and `inspect.py` if a CLI is added.
- Smoke preview showing R228 packet consumption, proposed contract preview, all live/order/config flags false, and recommended next operator action.
