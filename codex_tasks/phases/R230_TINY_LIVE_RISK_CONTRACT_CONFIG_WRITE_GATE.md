# R230 Tiny Live Risk Contract Config Write Gate

## Purpose

Consume the R229 tiny-live risk contract preview and create a guarded config-write gate for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

This future phase may write only the bounded risk-contract config if explicitly confirmed with an exact operator phrase and validated by tests. It must not enable live execution.

## Required Inputs

- latest `logs/hammer_radar_forward/tiny_live_risk_contract_preview.ndjson`
- latest R228 `tiny_live_10_of_10_ready_packet.ndjson`
- read-only current `configs/hammer_radar/tiny_live_risk_contracts.json`
- read-only current `configs/hammer_radar/lane_controls.json`

## Required Behavior

- Confirm latest R229 preview exists and is for the official lane.
- Confirm R229 `risk_contract_preview_ready=true`.
- Confirm R229 `approval_status=NOT_APPROVED_PREVIEW_ONLY`.
- Build a bounded config patch preview before writing.
- Require an exact config-write confirmation phrase.
- If not confirmed, write nothing.
- If confirmed, write only `configs/hammer_radar/tiny_live_risk_contracts.json`.
- Preserve lane controls and live flags.
- Keep risk-contract config write separate from live authorization.

## Non-Negotiable Safety

R230 must not:

- call Binance or any network
- place orders or test orders
- create executable order payloads
- sign trading or readonly requests
- transfer or withdraw
- enable live execution
- disable the kill switch
- set any lane `tiny_live`
- mutate env files
- mutate scheduler or fisherman configs
- mutate lane controls
- append paper outcomes, strategy performance, or promotion status
- promote any lane, alternate, signal origin, or betrayal path
- infer live readiness from the config write

## Validation Expectations

- preview writes no config
- wrong confirmation writes no config
- exact confirmation mutates only the risk-contract config
- config mutation is bounded to the official lane contract
- lane controls remain unchanged
- env remains unchanged
- no Binance/network/order/payload calls
- live authorization remains false
- order readiness remains false
