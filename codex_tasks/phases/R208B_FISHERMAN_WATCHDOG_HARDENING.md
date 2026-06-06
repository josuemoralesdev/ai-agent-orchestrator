# R208B Fisherman Watchdog Hardening

## Purpose

Make weekend paper fisherman watchdog behavior explicit and less dependent on
manual tmux loops.

## Required Scope

- Reuse R198/R176/R208/R208A local ledgers and heartbeat semantics.
- Define bounded watchdog status and restart recommendations.
- Make stale, exited-after-capture, missing-heartbeat, and no-signal states explicit.
- Keep any restart behavior operator-approved unless a future phase explicitly authorizes automation.

## Safety

- No systemd install unless explicitly approved.
- No systemd start, stop, restart, enable, or disable unless explicitly approved.
- No config writes.
- No env writes.
- No live execution.
- No Binance calls.
- No network calls.
- No order payloads.
- No lane mode mutation.
- No signal-origin or lane promotion.

## Expected Output

Produce an operator-safe watchdog hardening report and optional append-only
ledger record. Include exact manual commands for the operator when service or
tmux action is needed, but do not run them automatically.
