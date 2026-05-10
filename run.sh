#!/usr/bin/env bash
# run.sh — 빠른 실행 진입점
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 가상환경 자동 활성화
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

python cli.py "$@"
