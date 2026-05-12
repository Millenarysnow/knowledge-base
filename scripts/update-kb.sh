#!/bin/bash
# ============================================
# 智能知识库 - 定时增量更新
# 配合 crontab 使用
# 设置: (crontab -l; echo "0 2 * * * $(pwd)/scripts/update-kb.sh") | crontab -
# ============================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/../kb-update.log"

{
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 增量更新开始"
    "$SCRIPT_DIR/compile-wiki.sh" build
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 增量更新完成"
    echo "----------------------------------------"
} >> "$LOG_FILE" 2>&1
