#!/usr/bin/env bash
# 定时更新入口。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

LOG_FILE="$ROOT/data/kb-update.log"
mkdir -p "$ROOT/data"
{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] update start"
  if [ -n "${SYNC_FROM_ANYTHINGLLM:-}" ]; then
    if [ -n "${DEFAULT_DEPT:-}" ]; then
      python3 -m kb.cli update --sync-from-anythingllm --default-dept "$DEFAULT_DEPT"
    else
      python3 -m kb.cli update --sync-from-anythingllm
    fi
  else
    python3 -m kb.cli update
  fi
  if [ -n "${ANYTHINGLLM_API_KEY:-}" ]; then
    python3 -m kb.cli sync-anythingllm || true
  else
    echo "ANYTHINGLLM_API_KEY 未配置，跳过 AnythingLLM 同步"
  fi
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] update done"
  echo "----------------------------------------"
} >> "$LOG_FILE" 2>&1
