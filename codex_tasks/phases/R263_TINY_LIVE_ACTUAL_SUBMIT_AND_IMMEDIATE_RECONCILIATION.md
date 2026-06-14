# R263 Tiny-Live Actual Submit And Immediate Reconciliation

Implement the actual tiny-live submit phase only after prior live-control and final-console gates are complete.

Scope:
- Actual submit path for exactly three orders.
- Record exchange order ids.
- Immediate reconciliation.
- Partial success handling.
- No duplicate live submit.
- Preserve idempotency and abort semantics.
