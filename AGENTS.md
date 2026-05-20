# AGENTS.md

This repository contains the Kernel / Hammer Radar / Money Printing Machine project.

This file gives repo-local operating rules for AI coding agents working through Codex CLI.
It complements `codex_tasks/CODEX_RULES.md`, `README.md`, Hammer Radar docs, runbooks, and phase sexels.
It does not replace them.

## Project Identity

- Treat this repo as a trading research, paper execution, readiness, and operator-safety system.
- The active strategic objective is the Money Printing Machine / bull run 2026 path toward 888k USDT.
- The engineering objective is to evaluate signals, live statistics, strategy health, market context, and execution readiness.
- The system must stay machine-led but human-approved: 99% machine, 1% human approval.
- Do not turn this repo into the Architect dev-orchestrator. Architect may manage projects, but Hammer Radar logic stays scoped here unless a phase explicitly says otherwise.

## Instruction Sources

Before making changes, inspect the relevant instruction surfaces when present:

- `codex_tasks/CODEX_RULES.md`
- `README.md`
- `docs/hammer_radar/`
- `docs/hammer_radar_manual_tiny_live_protocol.md`
- phase-specific docs, especially recent R7x/R8x readiness, rehearsal, and protected live gate files
- existing tests related to the requested phase

If instructions conflict, prefer the safest interpretation and preserve live-trading protections.

## Non-Negotiable Trading Safety

- Never place real orders unless the user gives an explicit future-phase instruction that authorizes live execution.
- Never enable live execution flags unless the user explicitly requests that exact change.
- Never bypass human-in-the-loop approval gates.
- Never weaken paper/live separation.
- Never expose, print, commit, synthesize, or infer secrets, API keys, tokens, signatures, `.env` values, or auth headers.
- Never expose the approval API publicly. Keep operator surfaces bound to local/private access unless a future phase explicitly changes exposure.
- Never fund accounts, modify exchange account settings, or change Binance live permissions.
- Preserve kill switches, dry-run paths, readiness checks, rehearsal flows, review-only paths, and audit trails.

## Runtime Invariants

Preserve these safety outcomes unless a future explicitly approved live phase says otherwise:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `secrets_shown=false`
- live execution remains disabled by default
- global kill switch remains active by default
- vague live commands remain blocked
- raw `YES` remains rejected
- commands like `trade now live` remain blocked
- paper/operator visibility does not imply live approval
- readiness/status endpoints remain fast and safe

Any change touching these invariants must include tests or smoke checks proving the invariant still holds.

## Phase Workflow

- Work phase-by-phase.
- Use a new branch for each new phase unless the user explicitly says otherwise.
- Keep changes surgical and scoped to the requested phase.
- Do not commit, merge, tag, push, deploy, or restart services unless explicitly requested.
- Do not delete logs, state files, runtime artifacts, or service scripts.
- Preserve dirty worktree changes made by the user.
- If unexpected changes appear in files being edited, stop and report them.

## Phase Classification And Capability Reuse

Before implementing any new phase or task, Codex must classify the work as exactly one or more of:

- `NEW CAPABILITY`: a genuinely new behavior or surface that does not already exist in the repo.
- `EXTENSION OF EXISTING CAPABILITY`: expands something already present, such as an existing module, endpoint, CLI command, scheduler task, ledger, detector, risk contract, notification, or preflight.
- `WIRING / INTEGRATION`: connects existing pieces, adapts formats, adds source/consumer plumbing, or makes one subsystem consume another subsystem's output.
- `DIAGNOSTIC / AUDIT`: adds inspection, reporting, validation, summaries, review-only checks, or source-chain explanation.
- `DUPLICATE RISK`: resembles an existing module, endpoint, CLI command, ledger, scheduler task, report, or safety gate and must be checked carefully before implementation.

Codex must perform a lightweight capability scan before implementation. Inspect, at minimum when relevant:

- `docs/`
- `docs/hammer_radar/`
- `src/app/hammer_radar/operator/`
- `src/app/hammer_radar/execution/`
- `tests/hammer_radar/`
- `configs/`
- existing FastAPI routes
- existing CLI inspect commands
- existing scheduler tasks
- existing log/ledger file names referenced in code or docs
- existing risk contract, preflight, readiness, ticket, packet, and notification modules

Use available tools such as `rg`, `grep`, `find`, `git grep`, existing tests/docs, endpoint names, and CLI command names. If `rg` is unavailable, use `grep` or `find`; do not fail the scan just because one search tool is missing.

If an existing capability already solves 70% or more of the requested behavior:

- Prefer extending it instead of creating a new module.
- Prefer adding a small adapter or wiring layer instead of duplicating logic.
- Prefer updating docs/tests to reflect reuse.
- Only create a new module when it creates a clearly distinct boundary.

The phase classification process does not override safety requirements. For Hammer Radar / live trading work:

- No orders unless explicitly authorized by the correct live gate.
- No Binance live/trading calls unless explicitly authorized.
- No account/balance calls unless explicitly authorized.
- No executable payloads unless explicitly authorized.
- No env edits unless explicitly authorized.
- No secrets.
- No `AGENTS.md` edits unless the user explicitly asks for `AGENTS.md` changes.

When a repo has many phases or a long history, Codex should recommend or create a capability index doc when useful. For this repo, keep `docs/hammer_radar/PHASE_CAPABILITY_INDEX_R1_R100.md` current as future phases discover or extend capabilities.

## Engineering Standards

- Search for existing patterns before adding new helpers.
- Reuse existing modules, schemas, normalizers, and safety helpers.
- Preserve current behavior unless the sexel explicitly requests a behavior change.
- Prefer clear, boring, deterministic code over clever shortcuts.
- Avoid broad exception swallowing, silent fallbacks, fake-success responses, or hidden early returns.
- Keep API responses explicit about blocked, dry-run, paper, rehearsal, readiness, and live-disabled states.
- Keep tests close to the behavior being changed.
- Keep performance-sensitive operator endpoints fast.

## Environment

- Use the repo `.venv` for Python validation.
- Prefer `.venv/bin/python -m ...` over system Python.
- Do not assume system Python has project dependencies.
- Use local endpoints such as `127.0.0.1:8015` for smoke checks unless instructed otherwise.
- Do not edit `.env` files.
- Do not print environment values.
- Do not install packages globally unless explicitly instructed.

## Validation

Run the smallest useful validation first, then broaden when risk warrants.

Preferred validation forms:

- `.venv/bin/python -m py_compile ...`
- `PYTHONPATH=. .venv/bin/python -m pytest -q <targeted_tests>`
- `PYTHONPATH=. .venv/bin/python -m pytest -q` when scope warrants
- local curl smoke checks for operator/readiness endpoints when relevant

For trading or live-readiness work, final verification must report whether:

- live execution stayed disabled
- order placement stayed false
- real order placement stayed false
- execution attempt stayed false
- secrets stayed hidden
- kill switch behavior stayed intact
- paper/live separation stayed intact

If validation cannot run, report the exact reason and the exact command the user can run manually.

## Systemd And Runtime Services

- Do not start, stop, restart, enable, disable, or edit systemd services unless explicitly instructed.
- Known services may include:
  - `hammer-approval-api.service`
  - `hammer-telegram-polling.service`
  - other Hammer Radar or Kernel local services
- If a service action is needed, report the exact command instead of running it unless the user approved it.
- Preserve local-only bindings and existing ports unless the task explicitly changes them.

## Operator API And Telegram

- Treat the operator API as safety-critical.
- Preserve status, readiness, runbook, blocker, manual outcome, paper execution, strategy performance, and live-eligibility semantics.
- Telegram commands must remain explicit, normalized, audited, and safe.
- Telegram alerts for paper/operator visibility must not imply live authorization.
- Live command handling must remain conservative and blocked unless an approved phase defines an exact safe path.

## Strategy Scope

Hammer Radar strategy work may involve:

- hammer and shooting star detection
- RSI extremes and divergence
- golden pocket / Fibonacci levels
- multi-timeframe policy
- paper execution
- manual outcomes
- strategy promotion
- live-readiness scoring
- tiny-live rehearsal gates
- protected live gate review
- operator briefings and dashboards

Changes to strategy scoring, promotion, or live eligibility must preserve auditability and must not silently promote a strategy into live execution.

## Final Report Requirements

Every substantial Codex run must end with:

- branch name
- Phase Classification:
  - Primary classification:
  - Secondary classification(s):
  - Duplicate risk level: `LOW` / `MEDIUM` / `HIGH`
  - Reason:
- Capability Scan:
  - Existing docs checked:
  - Existing modules checked:
  - Existing tests checked:
  - Existing endpoints checked:
  - Existing CLI commands checked:
  - Existing scheduler tasks checked:
  - Existing logs/ledgers/configs checked:
- Reuse / Extend / Create Decision:
  - Existing capability reused:
  - Existing capability extended:
  - New capability created:
  - Why new code was necessary:
  - Why this is not duplicating prior work:
- Duplicate Risk Report:
  - Similar existing modules:
  - Similar existing endpoints:
  - Similar existing CLI commands:
  - Similar existing scheduler tasks:
  - Similar existing docs:
  - Risk:
  - Mitigation:
- files changed
- what changed and why
- tests or checks run
- smoke checks run, if any
- safety result:
  - live execution disabled or not
  - order placed or not
  - real order placed or not
  - execution attempted or not
  - secrets shown or not
- blockers, if any
- exact manual commands needed, if any

Do not end with vague "should work" language. Report verified facts.
