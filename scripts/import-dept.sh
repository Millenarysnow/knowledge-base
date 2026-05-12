#!/bin/bash
# ============================================
# 智能知识库 - 导入文档到指定部门
# 文件按日期组织: dept-XX/YYYY/MM/DD/分类/文件名
# 用法: ./import-dept.sh <部门名> <源文档目录>
# ============================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

if [ $# -lt 2 ]; then
    echo "用法: $0 <部门名称> <源文档目录>"
    echo ""
    echo "示例:"
    echo "  $0 研发部 /data/研发文档/"
    echo "  $0 财务部 /home/user/财务制度/"
    echo ""
    echo "导入后路径: volumes/documents/dept-研发部/$(date '+%Y/%m/%d')/分类/文件"
    exit 1
fi

DEPT_NAME="$1"
SOURCE_DIR="$2"
DEPT_DOC_DIR="$PROJECT_ROOT/volumes/documents/dept-$DEPT_NAME"
TODAY="$(date '+%Y/%m/%d')"

if [ ! -d "$SOURCE_DIR" ]; then
    echo -e "${RED}错误: 源目录不存在: $SOURCE_DIR${NC}"
    exit 1
fi

mkdir -p "$DEPT_DOC_DIR"

echo "=========================================="
echo "  智能知识库 - 部门文档导入"
echo "=========================================="
echo "  部门: $DEPT_NAME"
echo "  源目录: $SOURCE_DIR"
echo "  目标: dept-$DEPT_NAME/$TODAY/"
echo ""

COUNT=0

find "$SOURCE_DIR" -type f \( -iname "*.pdf" -o -iname "*.docx" -o -iname "*.doc" -o -iname "*.wps" -o -iname "*.ofd" -o -iname "*.md" -o -iname "*.txt" \) | while IFS= read -r file; do
    fname=$(basename "$file")
    fname_lower=$(echo "$fname" | tr '[:upper:]' '[:lower:]')

    # ---- 自动判定分类 ----
    CATEGORY="技术"  # 默认
    if echo "$fname_lower" | grep -qE "会议|纪要|讨论|决议|复盘|例会|评审"; then
        CATEGORY="会议"
    elif echo "$fname_lower" | grep -qE "报告|总结|汇报|分析|调研|统计|年度|季度|评估"; then
        CATEGORY="报告"
    elif echo "${fname_lower##*.}" | grep -qE "docx|doc|wps|ofd"; then
        CATEGORY="行政"
    fi

    DEST="$DEPT_DOC_DIR/$TODAY/$CATEGORY"
    mkdir -p "$DEST"
    cp -f "$file" "$DEST/"
    echo "  ✅ dept-$DEPT_NAME/$TODAY/$CATEGORY/$fname"
    COUNT=$((COUNT + 1))
done

echo ""
echo -e "${GREEN}✅ 导入完成${NC}"
echo "=========================================="
echo "  部门文档上传: http://localhost:8888/upload"
echo "  结构化浏览:   http://localhost"
echo "  智能问答:     http://localhost:8301"
echo "  问答范围:     公共区 + $DEPT_NAME 部门区"
echo "=========================================="
