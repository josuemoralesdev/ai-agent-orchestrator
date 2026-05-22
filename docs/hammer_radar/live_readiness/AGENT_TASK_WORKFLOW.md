# Agent Task Workflow

This runbook defines how to use specialized agent role files and phase task folders for Hammer Radar / Money Printing Machine work. It is workflow scaffolding only and does not change runtime trading behavior.

## Workflow

1. Operator chooses the phase.
2. Operator provides or selects a task file from `codex_tasks/phases/`.
3. Codex reads `AGENTS.md` and `codex_tasks/CODEX_RULES.md`.
4. Codex reads the specialized role files requested by the task:
   - `AGENTS.builder.md`
   - `AGENTS.index.md`
   - `AGENTS.qa.md`
   - `AGENTS.security.md`
5. Codex performs the required capability scan before editing.
6. Codex applies the builder, index, QA, and security perspectives listed in the task.
7. Codex implements only the requested phase.
8. Codex runs the required validation.
9. Codex reports only.
10. Operator manually commits, merges, and tags after reviewing the result.

## Required Phase Inputs

Every phase task should include:

- phase
- branch
- phase classification
- reason
- assigned agents
- main objective
- capability scan scope
- reuse / extend / create decision
- duplicate risk report
- files expected
- tests required
- validation commands
- safety constraints
- do-not section
- final report format

Use `codex_tasks/phases/PHASE_TASK_TEMPLATE.md` as the starting point.

## Agent Perspectives

Builder:
- implements only the requested phase
- reuses existing modules first
- avoids duplicate readiness engines
- runs scoped validation
- reports changed files and results

Index:
- maps existing capabilities before new work
- maintains phase indexes
- detects duplicate risk
- keeps R101-R106 and R107 docs linked
- maintains source-of-truth notes

QA / tester:
- runs focused tests first
- runs broader tests only when relevant
- validates shell scripts with `bash -n`
- reports exact pass/fail
- verifies safety assertions

Security:
- enforces live-trading boundaries
- checks secret handling
- confirms Telegram approval is not execution authority
- preserves dry-run and kill-switch discipline
- checks ledger permission failure awareness when ledgers are touched

## Reporting Agent Perspectives

The final phase report must state which perspectives were applied. Example:

```text
Agent perspectives applied: builder, index, qa, security
```

If a perspective was not applied, explain why.

## Branch And Tag Naming

Branch and tag names must differ.

- Branch example: `r107-first-live-execution-phase-design`
- Tag example: `r107`

Never use the same exact name for a branch and tag.

## Operational Rules

- No `sudo` inside Codex.
- No Git permission repair inside Codex.
- Operator handles commits manually unless explicitly delegated.
- Operator handles merges manually unless explicitly delegated.
- Operator handles tags manually unless explicitly delegated.
- Codex must not commit, merge, tag, push, deploy, or restart production services unless explicitly instructed.
- Do not start, stop, restart, enable, or disable systemd services unless explicitly instructed.

## Live Trading Rules

Live trading phases require explicit user authorization in the future phase task and in the current turn.

Unless explicitly authorized:

- do not enable live trading
- do not place orders
- do not call Binance order endpoints
- do not call account or balance endpoints
- do not modify env flags
- do not create live endpoints
- do not modify execution connector behavior
- do not expose secrets

Telegram approval is not execution authority. `FIRST_LIVE_ACTIVATION_READY` is only a prerequisite for a future explicitly authorized phase.

## Required Reports

Every substantial phase report must include:

- phase classification
- duplicate risk report
- capability scan summary
- reuse / extend / create decision
- files created and modified
- tests required and run
- validation results
- runtime behavior changed or not
- safety result
- blockers and manual commands, if any

