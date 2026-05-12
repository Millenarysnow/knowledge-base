#!/bin/bash
# ============================================
# 智能知识库 - 创建部门
# 用法: ./create-dept.sh <部门名称> [部门描述]
# 批量: ./scripts/import-users.sh users.csv
# ============================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

if [ $# -lt 1 ]; then
    echo "用法: $0 <部门名称> [部门描述]"
    echo ""
    echo "单个创建:"
    echo "  $0 研发部"
    echo ""
    echo "批量导入（推荐）:"
    echo "  ./scripts/import-users.sh users.csv"
    exit 1
fi

DEPT_NAME="$1"
DEPT_DIR="$PROJECT_ROOT/volumes/documents/dept-$DEPT_NAME"
USERS_DIR="$PROJECT_ROOT/volumes/users"

mkdir -p "$USERS_DIR"

if [ -d "$DEPT_DIR" ]; then
    echo -e "${YELLOW}⚠ 部门已存在: $DEPT_NAME${NC}"
else
    mkdir -p "$DEPT_DIR"
    echo -e "${GREEN}✅ 创建部门: $DEPT_NAME${NC}"

    # 写入部门记录
    if [ ! -f "$USERS_DIR/depts.csv" ]; then
        echo "dept_name,created_at" > "$USERS_DIR/depts.csv"
    fi
    echo "$DEPT_NAME,$(date '+%Y-%m-%d %H:%M:%S')" >> "$USERS_DIR/depts.csv"
fi

echo ""
echo "=========================================="
echo "  部门: $DEPT_NAME"
echo "  文档目录: volumes/documents/dept-$DEPT_NAME/"
echo "  路径格式: dept-$DEPT_NAME/YYYY/MM/DD/分类/文件"
echo ""
echo "  批量导入文档:"
echo "    ./scripts/import-dept.sh $DEPT_NAME /path/to/docs/"
echo ""
echo "  网页上传:"
echo "    http://localhost:8888/upload"
echo "=========================================="
