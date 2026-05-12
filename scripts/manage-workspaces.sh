#!/bin/bash
# ============================================
# 智能知识库 - AnythingLLM Workspace 管理
# 为每个部门创建独立 workspace 实现问答隔离
#
# 用法:
#   ./manage-workspaces.sh init        # 为所有部门创建workspace
#   ./manage-workspaces.sh create <部门名> <编码>
# ============================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ADMIN_PW=$(grep '^ADMIN_PASSWORD=' "$PROJECT_ROOT/.env" 2>/dev/null | cut -d'=' -f2- || echo "admin123")
API_BASE="http://localhost:8301/api/v1"
AUTH="Authorization: Bearer $ADMIN_PW"
ACTION="${1:-}"

create_workspace() {
    local name="$1"; local slug="$2"

    # 检查是否已存在
    local exists
    exists=$(curl -s -H "$AUTH" "$API_BASE/workspaces" 2>/dev/null | \
        python3 -c "import sys,json;d=json.load(sys.stdin);ws=d.get('workspaces',[]);print('yes' if any(w.get('slug','')=='$slug' for w in ws) else 'no')" 2>/dev/null || echo "no")

    if [ "$exists" = "yes" ]; then
        echo "  ⚠ Workspace '$name' 已存在，跳过"
        return
    fi

    local resp
    resp=$(curl -s -w "\n%{http_code}" -X POST "$API_BASE/workspace/new" \
        -H "$AUTH" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"$name\",\"slug\":\"$slug\"}" 2>/dev/null)
    local code; code=$(echo "$resp" | tail -1)

    if [ "$code" = "200" ] || [ "$code" = "201" ]; then
        echo "  ✅ Workspace '$name' ($slug) 创建成功"
    else
        echo "  ⚠ Workspace '$name' 创建返回状态: $code"
    fi
}

do_init() {
    echo "正在为所有部门创建 AnythingLLM workspace..."

    # 公共 workspace
    create_workspace "公共知识库" "public"

    # 从 departments.json 或文件系统读取部门列表
    local dept_file="$PROJECT_ROOT/volumes/db/departments.json"
    if [ -f "$dept_file" ]; then
        python3 -c "
import json
with open('$dept_file') as f:
    data = json.load(f)
for d in data.get('departments', []):
    print(d['name'])
" 2>/dev/null | while read -r name; do
            [ -z "$name" ] && continue
            local slug
            slug=$(echo "$name" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g')
            create_workspace "$name" "$slug"
        done
    else
        ls -d "$PROJECT_ROOT/volumes/documents/dept-"*/ 2>/dev/null | while read -r d; do
            local name; name=$(basename "$d" | sed 's/^dept-//')
            local slug
            slug=$(echo "$name" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g')
            create_workspace "$name" "$slug"
        done
    fi

    echo ""
    echo "=========================================="
    echo "  Workspace 创建完成"
    echo "=========================================="
    echo "  下一步（手动操作）:"
    echo "  1. 访问 http://localhost:8301"
    echo "  2. 为每个部门 workspace 配置挂载目录:"
    echo "     - 公共 workspace: /app/hostdocuments/source/public/"
    echo "     - 部门 workspace: /app/hostdocuments/source/public/"
    echo "                       + /app/hostdocuments/source/dept-<部门>/"
    echo "  3. 在 AnythingLLM 界面添加用户并分配 workspace"
    echo "=========================================="
}

case "$ACTION" in
    init) do_init ;;
    *)
        echo "用法: $0 init    为所有部门创建 AnythingLLM workspace"
        echo ""
        echo "详细说明:"
        echo "  此脚本调用 AnythingLLM API 为每个部门创建独立 workspace，"
        echo "  以实现问答时的部门文档隔离。创建后还需手动:"
        echo "  - 在 AnythingLLM 界面为每个 workspace 配置文档目录"
        echo "  - 将用户分配到对应 workspace"
        ;;
esac
