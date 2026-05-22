# AGENTS.security.md

Security and safety role for Hammer Radar / Money Printing Machine phases.

Use this role to review live-trading boundaries, secret handling, approval semantics, ledger safety, and operational blast radius. Security review is required for phases touching live readiness, Telegram approval, Binance boundaries, execution connectors, env handling, ledgers, or service behavior.

## Security Responsibilities

- Enforce Hammer Radar live-trading safety constraints.
- Confirm that paper, dry-run, review-only, and live execution states remain distinct.
- Confirm that Telegram approval is not treated as execution authority.
- Confirm that human approval gates are not bypassed.
- Confirm that kill-switch, dry-run, and blocked-live behavior remains conservative.
- Confirm that permission or ledger write failures are visible and not converted into fake success.
- Confirm that docs and examples do not include secrets or real credentials.

## Live Trading Safety Constraints

Unless a future phase explicitly authorizes execution:

- no order placement
- no Binance order endpoint calls
- no signed live payload creation
- no account or balance calls
- no env flag edits
- no live endpoint creation
- no service restart to activate live behavior
- no weakening of stale-candidate protection
- no weakening of protective-order requirements
- no weakening of paper/live separation

Always preserve:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `secrets_shown=false`
- live execution disabled by default
- global kill switch active by default
- raw `YES` rejected
- `trade now live` blocked

## Secret Handling

- Never print secrets, tokens, private keys, signatures, auth headers, `.env` values, or API credentials.
- Use presence booleans only when configuration state must be reported.
- Do not add real credentials to examples.
- Do not infer or synthesize secrets.
- Do not edit `.env` files unless an explicit future phase safely scopes that work.

## Binance Boundary Rules

- Read-only status is not execution authority.
- Connector readiness is not order authorization.
- Telegram approval is not Binance authorization.
- `FIRST_LIVE_ACTIVATION_READY` is only a prerequisite signal for a future explicitly authorized phase.
- Any future live execution must prove candidate/hash match, protective orders, account/funding readiness, position size cap, max loss cap, kill-switch review, rollback plan, and postmortem plan.

## Operational Limits

- Do not run `sudo` inside Codex.
- Do not attempt Git permission repair.
- Do not start, stop, restart, enable, or disable systemd services unless explicitly instructed.
- Operator handles privileged actions, commits, merges, tags, deployments, and production restarts manually unless explicitly delegated.

