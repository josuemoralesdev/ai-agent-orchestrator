# CODEX RULES

These rules are non-negotiable.

## Runtime
- Use the repo-local .venv for validation commands when running Python locally.
- Do not rely on system python for tests or imports.
- Prefer `.venv/bin/python -m ...` over `python -m ...` unless inside Docker.

## Scope Control
- Make the smallest safe change needed for the requested phase.
- Do not introduce live trading, Binance API keys, order execution, or secret handling unless the task explicitly asks for it.
- Preserve existing Hammer Radar behavior unless the task explicitly asks to change it.
- Do not delete existing logs, state files, or runtime scripts.
- Do not remove or replace systemd behavior in this phase.

## Safety
- Never commit secrets.
- Never print secrets.
- Never add real API keys to files.
- Do not place live trading credentials in examples.
- Any trading-related code must default to dry-run or paper mode unless explicitly approved in a future phase.

## Validation
- Run focused validation first.
- Run import/compile checks.
- If Docker files are changed, validate Docker build or explain exactly why it could not be validated.
- Paste clear validation output.

## Git
- Work on the current phase branch unless instructed otherwise.
- Do not merge or tag.
- Recommend commit, merge, and tag only after validation passes.
