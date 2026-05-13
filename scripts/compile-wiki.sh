#!/usr/bin/env bash
# 兼容旧入口：新的实现请使用 python -m kb.cli 或 scripts/kbctl.sh。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

usage() {
  cat <<'EOF'
智能知识库 kbctl

旧命令兼容：
  compile-wiki.sh build
  compile-wiki.sh status

新命令：
  scripts/kbctl.sh init
  scripts/kbctl.sh import-docs --zone public --source ./files --metadata ./file_meta.csv --sign-records ./sign.csv
  scripts/kbctl.sh build-site
  scripts/kbctl.sh sync-anythingllm
EOF
}

cmd="${1:-}"
case "$cmd" in
  build)
    python3 -m kb.cli build-site
    ;;
  status)
    python3 -m kb.cli status
    ;;
  import)
    echo "旧 import 命令已废弃，请改用：scripts/kbctl.sh import-docs ..."
    exit 1
    ;;
  *)
    usage
    ;;
esac
