#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/home/josue/workspace/kernel/ai-agent-orchestrator-main"
cd "${REPO_ROOT}"

PYTHONPATH=. .venv/bin/python - <<'PY'
from __future__ import annotations

from src.app.hammer_radar.operator.strategy_lab_variant_test_pack import (
    build_strategy_lab_variant_test_pack,
    format_strategy_lab_variant_test_pack_text,
)

payload = build_strategy_lab_variant_test_pack(log_dir="logs/hammer_radar_forward", write=False)
print(format_strategy_lab_variant_test_pack_text(payload, top_limit=10))
PY
