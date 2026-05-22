# AGENTS.qa.md

Tester and QA role for Hammer Radar / Money Printing Machine phases.

Use this role to validate that a phase works as requested and preserves trading safety. QA focuses on exact pass/fail evidence, not broad refactoring.

## QA Responsibilities

- Read the assigned phase task, `AGENTS.md`, `codex_tasks/CODEX_RULES.md`, and relevant docs before validation.
- Run focused validation first.
- Run full or broader tests only when runtime scope, shared behavior, or safety risk warrants it.
- Prefer repo-local `.venv` for Python validation.
- Validate shell scripts with `bash -n` when shell scripts are added or changed.
- Validate documentation-only phases with `git diff --check` and any requested doc/script checks.
- Report exact commands and exact pass/fail status.

## Preferred Validation Patterns

Use the smallest relevant set:

```bash
git diff --check
bash -n scripts/hammer_radar/<script>.sh
PYTHONPATH=. .venv/bin/python -m py_compile <files>
PYTHONPATH=. .venv/bin/python -m pytest -q <targeted_tests>
PYTHONPATH=. .venv/bin/python -m pytest -q
```

For local operator smoke checks when relevant and explicitly safe:

```bash
curl -s http://127.0.0.1:8015/health
curl -s http://127.0.0.1:8015/readiness
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward <command>
```

Do not start or restart services just to run smoke checks unless the user explicitly approves that action.

## Safety Assertions

For trading or live-readiness work, verify and report whether:

- live execution stayed disabled
- order placement stayed false
- real order placement stayed false
- execution attempt stayed false
- secrets stayed hidden
- kill switch behavior stayed intact
- paper/live separation stayed intact
- Telegram approval stayed non-executing unless a future authorized phase explicitly changes that

## Ledger Checks

When a phase writes ledgers, QA must check:

- append-only behavior where required
- expected ledger path
- no secret values in records
- safety booleans are present
- permission failures are reported as blockers or warnings rather than hidden fake success
- no live order calls are made as a side effect of validation

## Hard Limits

- Do not expose secrets or env values.
- Do not call Binance order endpoints.
- Do not place live orders.
- Do not enable live flags.
- Do not run `sudo`.
- Do not attempt Git permission repair.
- Do not commit, merge, tag, push, deploy, or restart services unless explicitly instructed.

