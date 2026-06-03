# R178 Risk Contract Apply Packet If Evidence Ready

## Phase

R178 Risk Contract Apply Packet If Evidence Ready for BTCUSDT 8m Short

## Classification

- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk: MEDIUM

## Purpose

Build a future risk-contract apply packet for `BTCUSDT|8m|short|ladder_close_50_618` only after R177 shows:

- fresh captures are at least 10 / 10
- R158 short evidence is ready for operator review
- funding context has been rechecked
- risk contract context still needs a safe apply packet

R178 is useful only after captures are `>=10` and evidence is ready. It must remain preview-only by default.

## Non-Negotiables

- Do not write risk-contract config by default.
- Do not mutate lane config.
- Do not set the short lane `tiny_live`.
- Do not enable live execution.
- Do not disable the kill switch.
- Do not call Binance.
- Do not create executable payloads.
- Do not place orders.
- Do not transfer or withdraw.
- Do not mutate env files.
- Do not print secrets.

## Required Inputs

- R177 evidence threshold recheck output
- R158 short evidence recheck packet output
- R162 short risk-contract apply review output
- R174 funding context output
- existing R161 draft preview if available

## Expected Output

Produce a packet that states:

- whether R177 evidence readiness is sufficient to continue
- whether the target risk contract draft exists
- what config patch would be needed in a future apply phase
- which gates still block application
- exact next safe operator move
- exact `do_not_run_yet` list
- safety object with all live/order/Binance/config mutation flags false

## Safety Boundary

R178 must not become execution authority. It may prepare a review packet only. Any future config write must require a separate explicit phase, exact confirmation phrase, tests, and no live execution.
