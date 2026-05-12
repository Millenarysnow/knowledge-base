#!/bin/bash
# ============================================
# 智能知识库 - 模型拉取引导脚本
# 自动拉取 .env 中配置的对话模型和嵌入模型
#
# 用法:
#   ./pull-models.sh
#   ./pull-models.sh qwen2.5:14b    # 指定模型
# ============================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 从 .env 读取配置
[ -f "$PROJECT_ROOT/.env" ] && source "$PROJECT_ROOT/.env" 2>/dev/null || true

CHAT_MODEL="${1:-${OLLAMA_MODEL:-qwen2.5:7b}}"
EMBED_MODEL="${EMBEDDING_MODEL:-bge-m3}"

echo "=========================================="
echo "  智能知识库 - 模型拉取"
echo "=========================================="
echo "  对话模型: $CHAT_MODEL"
echo "  嵌入模型: $EMBED_MODEL"
echo "=========================================="
echo ""

if ! docker ps 2>/dev/null | grep -q kb-ollama; then
    echo "错误: Ollama 容器未运行，请先执行 docker compose up -d"
    exit 1
fi

echo "拉取对话模型: $CHAT_MODEL"
docker exec kb-ollama ollama pull "$CHAT_MODEL"

echo ""
echo "拉取嵌入模型: $EMBED_MODEL"
docker exec kb-ollama ollama pull "$EMBED_MODEL"

echo ""
echo "=========================================="
echo "  模型就绪！当前已安装的模型:"
echo "=========================================="
docker exec kb-ollama ollama list
echo "=========================================="
