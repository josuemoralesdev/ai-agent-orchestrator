# R169 Env Role Split Proposal No Write

## Phase

R169 Env Role Split Proposal No Write

## Classification

- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, DUPLICATE RISK
- Duplicate risk: HIGH

## Purpose

Propose clean, unambiguous env naming for Binance key roles after R168 proved that market/read-only and account-read key roles can be confused.

R169 must produce a proposal only. It must not write env files by default.

## Required Proposal Scope

Define a safe naming and loading plan for:

- market data key
- account read key
- live trading key or future account key

The proposal should cover:

- recommended env variable names
- recommended local env file names
- which role may be used for read-only balance checks
- which role may be used for market-data/status checks
- which role remains disabled until an explicitly approved future live phase
- how runtime flags must force read-only behavior for account-balance checks
- how future code should avoid mismatched key/secret pairs

## Non-Negotiables

- Do not place orders.
- Do not call Binance order, test-order, protective, transfer, or withdraw endpoints.
- Do not call Binance account/balance endpoints.
- Do not enable live trading.
- Do not print secrets.
- Do not print full API keys.
- Do not mutate `.env`.
- Do not mutate env files.
- Do not mutate config files.
- Do not change lane modes.
- Do not set short tiny_live.
- Do not write risk-contract config.
- Do not run sudo.
- Do not commit, merge, or tag.

## Expected Output

Create a proposal doc under:

```text
docs/hammer_radar/live_readiness/R169_ENV_ROLE_SPLIT_PROPOSAL_NO_WRITE.md
```

The doc should include:

- role inventory
- proposed env names
- proposed file names
- safe load commands for operator review
- migration checklist
- no-write default
- explicit future approval gates required before any write
- safety boundary

## Validation

Run the smallest useful checks for docs-only work:

```bash
git diff -- .env || true
git diff -- configs/hammer_radar/tiny_live_risk_contracts.json || true
git diff -- configs/hammer_radar/lane_controls.json || true
```

Report that no env/config mutation occurred.
