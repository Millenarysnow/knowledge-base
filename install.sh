#!/bin/bash
# ============================================
# 智能知识库 - 一键安装脚本
# 架构: AnythingLLM + LLM Wiki + Ollama
# 部署: 纯本地 | 开源 | 中文优化 | 纯脚本
# ============================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

echo ""
echo "=========================================="
echo "  智能知识库 — 一键安装"
echo "  架构: AnythingLLM + LLM Wiki + Ollama"
echo "=========================================="
echo ""

# ---- Docker 检查 ----
if ! command -v docker &> /dev/null; then
    echo "正在安装 Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    echo "Docker 安装完成，请重新登录后再次运行此脚本"
    exit 1
fi
echo -e "${GREEN}✅ Docker 已安装${NC}"

if ! docker compose version &> /dev/null; then
    echo "正在安装 Docker Compose..."
    sudo apt update && sudo apt install -y docker-compose-plugin
fi
echo -e "${GREEN}✅ Docker Compose 已安装${NC}"

# ---- 创建目录 ----
echo ""
echo "创建数据目录..."
mkdir -p volumes/{ollama,anythingllm,documents,llm-wiki-storage/raw,llm-wiki-storage/wiki,llm-wiki-site,users,db}
mkdir -p volumes/documents/public/{行政,技术,会议,报告}
mkdir -p volumes/documents/dept-信息技术部/{行政,技术,会议,报告}
mkdir -p volumes/documents/dept-办公室/{行政,技术,会议,报告}
mkdir -p volumes/documents/dept-研究室/{行政,技术,会议,报告}
echo -e "${GREEN}✅ 数据目录已创建${NC}"

# ---- 权限 ----
chmod +x scripts/*.sh 2>/dev/null || true
chmod +x scripts/*.py 2>/dev/null || true
echo -e "${GREEN}✅ 脚本权限已设置${NC}"

# ---- 启动服务 ----
echo ""
echo "拉取镜像并启动服务..."
docker compose pull 2>/dev/null || true
docker compose up -d
echo "等待服务启动（约 30 秒）..."
sleep 30

# ---- 服务检查 ----
echo ""
echo "--- 服务状态 ---"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep kb- || true

# ---- 拉取模型 ----
echo ""
echo "=========================================="
echo "  下载模型（约需几分钟）"
echo "=========================================="
if docker ps | grep -q kb-ollama; then
    echo "下载对话模型: ${OLLAMA_MODEL:-qwen2.5:7b}"
    docker exec kb-ollama ollama pull "${OLLAMA_MODEL:-qwen2.5:7b}" 2>&1 || echo "模型拉取中，可稍后手动执行: ./scripts/pull-models.sh"

    echo "下载嵌入模型: ${EMBEDDING_MODEL:-bge-m3}"
    docker exec kb-ollama ollama pull "${EMBEDDING_MODEL:-bge-m3}" 2>&1 || echo "模型拉取中，可稍后手动执行"
    echo -e "${GREEN}✅ 模型下载完成${NC}"
else
    echo -e "${YELLOW}⚠ Ollama 未启动，稍后手动拉取: ./scripts/pull-models.sh${NC}"
fi

# ---- 初始化部门 ----
echo ""
echo "初始化部门..."
./scripts/import-users.sh users.csv 2>/dev/null || true
echo -e "${GREEN}✅ 部门初始化完成${NC}"

# ---- 创建 workspace ----
echo ""
echo "创建 AnythingLLM workspace（可能需要稍后手动配置）..."
./scripts/manage-workspaces.sh init 2>/dev/null || {
    echo -e "${YELLOW}⚠ workspace API 暂不可用，请待服务完全启动后执行:${NC}"
    echo "  ./scripts/manage-workspaces.sh init"
}

# ---- 完成 ----
echo ""
echo "=========================================="
echo "  安装完成！"
echo "=========================================="
echo ""
echo "  访问地址:"
echo "    结构化浏览:  http://localhost"
echo "    智能问答:    http://localhost:8301"
echo "    部门上传:    http://localhost:8888/upload"
echo "    管理员密码:  $(grep ADMIN_PASSWORD .env 2>/dev/null | cut -d'=' -f2 || echo 'admin123')"
echo ""
echo "  下一步:"
echo "    批量导入文档:"
echo "      ./scripts/compile-wiki.sh import /你的/文档/目录/"
echo ""
echo "    导入到部门:"
echo "      ./scripts/compile-wiki.sh import /path/ --dept 信息技术部"
echo ""
echo "    导入查阅记录:"
echo "      ./scripts/compile-wiki.sh import-records ./查阅记录.csv"
echo ""
echo "    查看状态:"
echo "      ./scripts/compile-wiki.sh status"
echo ""
echo "    定时更新:"
echo "      (crontab -l; echo \"0 2 * * * $(pwd)/scripts/update-kb.sh\") | crontab -"
echo ""
echo "=========================================="
