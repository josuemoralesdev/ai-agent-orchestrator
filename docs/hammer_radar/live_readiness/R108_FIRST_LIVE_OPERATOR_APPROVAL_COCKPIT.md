# R108 First-Live Operator Approval Cockpit

Phase: R108

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, DUPLICATE RISK
- Duplicate risk level: HIGH

## What R108 Adds

R108 adds a minimal first-live operator cockpit over the existing R102-R106 readiness chain:

- `GET /operator/approval-cockpit`
- `GET /operator/approval-cockpit/state`
- `POST /operator/approval-cockpit/intent`

The cockpit shows candidate readiness, the required gate sequence, simultaneous candidate/operator signal cards, counsel decision metadata, approval-window countdowns, blockers, warnings, and clear safety labels.

Approval and rejection buttons record operator intent only in:

```text
operator_approval_cockpit_intents.ndjson
```

## What R108 Does Not Add

R108 does not add:

- live trading
- live env changes
- Binance order calls
- account or balance calls
- signed order payload creation
- a live order endpoint
- execution authority
- approval-to-execution wiring
- Telegram approval-to-execution wiring
- service restarts

## UI Concept

The cockpit is a static HTML/JS page served by the existing approval API. It uses no external CDN and no frontend framework.

The first screen is intentionally direct:

- `INTENT ONLY`
- `NO ORDER WILL BE PLACED`
- `R106 GATE AUTHORITY`
- `live_ready=false`
- `execution_enabled_by_ui=false`
- `order_placed=false`
- `real_order_possible=false`

Buttons are large and visually prominent, but every button is scoped to intent recording only.

## Sequence Approval Model

The sequence view shows the required order:

1. final preflight
2. armed dry run
3. one tiny live order protocol
4. first live activation gate
5. operator approval intent
6. confirmation phrase requirement

Each step includes status, required flag, blocker count, `can_approve`, and `expires_at_utc` where relevant.

The cockpit does not recompute these gates as a new source of truth. It composes:

- R102 final live preflight
- R104 tiny-live armed dry run
- R105 one tiny live order protocol
- R106 first-live activation gate

## Simultaneous Signal Approval Model

The simultaneous signal view shows candidate/operator decision cards when candidate metadata exists. Each card includes:

- candidate id
- symbol
- timeframe
- direction
- score when available
- counsel decision
- tags
- approval-window status
- seconds remaining
- whether intent can be recorded
- blockers
- warnings

This view is diagnostic and review-only. It does not select, arm, or execute a signal.

## Counsel Decision Tags

The intent endpoint accepts:

- `intent`: `APPROVE`, `REJECT`, or `WAIT`
- `counsel_decision`: `APPROVE`, `REJECT`, `WAIT`, or `ESCALATE`
- `counsel_tags`: short normalized tags
- optional `operator_note`

Tags are stored in the append-only cockpit intent ledger with the event type:

```text
OPERATOR_APPROVAL_COCKPIT_INTENT
```

## Hourglass / Countdown Approval Window Behavior

The state endpoint reports:

- `approval_window_opened_at_utc`
- `approval_window_expires_at_utc`
- `approval_window_seconds_remaining`
- `approval_window_status`: `OPEN`, `EXPIRED`, or `MISSING`

The window is derived from the current R106 gate evidence timestamp and only opens when candidate/hash data exists. The UI displays an hourglass/countdown and disables buttons unless the window is open and R106 is ready.

## Expired Approval Behavior

Expired windows disable UI approval buttons.

The backend also rejects intent recording when the window is not `OPEN`. Rejected valid-shape attempts are recorded as ledger rows with:

- `accepted_as_intent=false`
- `rejection_reason`
- safety booleans proving no execution occurred

Malformed request shapes are rejected by API validation and do not become approval authority.

## Backend Authority Model

R106 remains the authority for first-live activation readiness.

R108 only renders and records intent around the R106 chain. The cockpit state explicitly reports:

- `backend_authority.r106_first_live_activation_gate`
- `backend_authority.ui_approval_is_execution_authority=false`
- `backend_authority.telegram_approval_is_execution_authority=false`
- confirmation phrase requirement

## Why UI Approval Is Not Execution Authority

UI approval is not execution authority because:

- the endpoint writes only an intent ledger row
- it never imports or calls an order-submit path
- it never changes env flags
- it never enables execution
- it never creates a live order endpoint
- it always returns `live_ready=false`
- it always returns `execution_enabled_by_ui=false`
- it always returns `order_placed=false`
- it always returns `execution_attempted=false`
- it always returns `real_order_possible=false`

Any future execution phase must still be separately and explicitly authorized.

## Safety Constraints

R108 preserves:

- no live orders
- no Binance order endpoint calls
- no account or balance calls
- no env edits
- no secret exposure
- no Telegram approval-to-execution wiring
- no UI approval-to-execution wiring
- no executable payload creation
- no live order endpoint
- paper/live separation
- R106 gate authority

## How This Prepares Future R109

R109 should review and harden the cockpit before any future dry authorization or execution-adjacent phase. R109 should verify:

- state composition remains source-of-truth aligned
- expired windows cannot be approved
- counsel metadata remains auditable
- UI labels remain unambiguous
- no execution authority exists
- ledger records are append-only and safe
- R106 remains the backend authority
