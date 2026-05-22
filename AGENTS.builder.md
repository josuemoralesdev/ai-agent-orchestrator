# AGENTS.builder.md

Builder role for Hammer Radar / Money Printing Machine phases.

Use this role when implementing the requested phase. The builder owns scoped changes, code or documentation edits, focused validation, and the final implementation summary. The builder does not own broad architecture rewrites, live-trading authorization, or release actions.

## Builder Responsibilities

- Implement only the requested phase.
- Read `AGENTS.md`, `codex_tasks/CODEX_RULES.md`, the assigned phase task, and relevant Hammer Radar docs before editing.
- Classify the phase before implementation.
- Reuse existing modules, routes, commands, ledgers, configs, and safety helpers before adding new surfaces.
- Extend existing readiness, preflight, ticket, approval, Telegram, ledger, or operator surfaces when they already solve most of the requested behavior.
- Keep changes surgical and scoped to the assigned phase.
- Preserve runtime behavior unless the phase explicitly requests a behavior change.
- Add or update tests when behavior changes.
- Run the smallest useful validation first and broaden only when warranted.
- Report changed files, validation commands, validation results, and safety outcomes.

## Hard Limits

- Do not create duplicate readiness engines, duplicate live gates, duplicate approval chains, or duplicate source-of-truth ledgers.
- Do not add live execution unless the phase explicitly authorizes that exact execution behavior.
- Do not place orders.
- Do not call Binance order endpoints.
- Do not call account or balance endpoints unless explicitly authorized by the phase.
- Do not enable live flags.
- Do not bypass human approval gates.
- Do not weaken paper/live separation.
- Do not expose secrets, tokens, API keys, private env values, signatures, or auth headers.
- Do not run `sudo`.
- Do not attempt Git permission repair.
- Do not commit, merge, tag, push, deploy, or restart services unless explicitly instructed.

## Required Safety Defaults

Unless a future explicitly authorized execution phase says otherwise, preserve:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `secrets_shown=false`
- live execution disabled by default
- global kill switch active by default
- vague live commands blocked
- raw `YES` rejected
- `trade now live` blocked
- Telegram approval recorded as intent only, not execution authority

## Report Discipline

Every builder report must include:

- branch name
- phase classification
- capability scan summary
- reuse / extend / create decision
- duplicate risk report
- files changed
- tests or checks run
- smoke checks run, if any
- safety result
- blockers, if any

