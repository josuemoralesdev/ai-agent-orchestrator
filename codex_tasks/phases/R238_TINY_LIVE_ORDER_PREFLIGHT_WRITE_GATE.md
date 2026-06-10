# R238 Tiny-Live Order Preflight Write Gate

## Intent

Consume the R237 tiny-live order-preflight preview and create a guarded order-preflight write gate.

## Required Boundaries

- Require an exact operator confirmation phrase before appending any R238 ledger record.
- Append only a local bounded order-preflight write-gate ledger record.
- Do not mutate env files.
- Do not mutate configs.
- Do not mutate `configs/hammer_radar/lane_controls.json`.
- Do not mutate `configs/hammer_radar/tiny_live_risk_contracts.json`.
- Do not create an executable order payload.
- Do not create a signed order request.
- Do not create a signed trading request.
- Do not call Binance or any network endpoint.
- Do not place a real order.
- Do not place a test order.
- Do not disable the kill switch.

## Inputs

- latest R237 order-preflight preview record
- latest R236 lane-arm write gate record
- latest R234 live execution enable write gate record
- latest R232 live authorization write gate record
- latest R230 risk contract config write gate record
- current read-only tiny-live risk contract config
- current read-only lane controls
- latest R228 evidence packet

## Output

Create a R238 preview/write-gate module and inspect CLI command that can append only its own local ledger record after exact confirmation. The R238 artifact should prove order-preflight requirements were reviewed, but it must not create order payloads or connect to Binance.
