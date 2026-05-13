#!/usr/bin/env bash
# 兼容入口：转发到新的 kbctl。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "错误：未找到 python3"
  exit 1
fi

python3 -m pip install -r requirements.txt
python3 -m kb.cli init

echo "初始化完成。"
echo "启动服务：docker compose up -d"
echo "查看文档：README.md / docs/OPERATIONS.md"
