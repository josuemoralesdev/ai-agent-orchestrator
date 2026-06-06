# R210 Betrayal True Inverse Refresh

## Purpose

Refresh betrayal true inverse paper validation using local evidence only.

## Required Scope

- Read R80/R81/R96-R100 betrayal docs and ledgers.
- Read R209 betrayal integration recheck records.
- Try to connect the latest 222m full-spectrum capture into actual true inverse paper tracking if the existing schema supports it.
- Keep naive inverse audit math separate from validated true inverse outcomes.
- Report whether 222m and 88m have enough resolved true inverse samples for future paper review.

## Safety

- No config writes.
- No env writes.
- No live execution.
- No Binance calls.
- No network calls.
- No order payloads.
- No transfers or withdrawals.
- No signal-origin promotion.
- No lane promotion.
- No betrayal live authorization.

## Expected Output

Produce a paper-only validation refresh report and optional append-only ledger
record behind an exact confirmation phrase.

The report must explicitly state whether each candidate is:

- unresolved
- insufficient sample
- ready for paper matrix context
- rejected for true inverse validation

No status may imply live readiness.
