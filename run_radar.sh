#!/usr/bin/env bash
set -e

cd /home/josue/workspace/kernel/ai-agent-orchestrator
source .venv/bin/activate
exec python -m src.app.hammer_radar.main
