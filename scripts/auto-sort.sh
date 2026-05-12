#!/bin/bash
# ============================================
# 智能知识库 - 自动归类
# 对目录下散乱文件按关键字归类到 行政/技术/会议/报告
# 规则：文件名字段 > 扩展名 > 内容关键字，不盲目按扩展名分类
# 用法: ./auto-sort.sh [目标目录]
# ============================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TARGET_DIR="${1:-$PROJECT_ROOT/volumes/documents}"

GREEN='\033[0;32m'; NC='\033[0m'

echo "=========================================="
echo "  智能知识库 — 自动归类"
echo "  目标: $TARGET_DIR"
echo "=========================================="

sort_file() {
    local file="$1"
    local fname; fname=$(basename "$file")
    local fname_lower; fname_lower=$(echo "$fname" | tr '[:upper:]' '[:lower:]')

    # 优先：文件名关键字
    if echo "$fname_lower" | grep -qE "会议|纪要|讨论|决议|复盘|例会|评审|座谈|研讨"; then
        echo "会议"; return
    fi
    if echo "$fname_lower" | grep -qE "报告|总结|汇报|分析|调研|统计|年度|季度|月度|评估"; then
        echo "报告"; return
    fi
    if echo "$fname_lower" | grep -qE "制度|管理|办法|规定|流程|规范|通知|公告|行政|考勤|薪酬|人事|财务|审计|合同"; then
        echo "行政"; return
    fi

    # 其次：扩展名提示（仅作弱信号）
    local ext="${fname_lower##*.}"
    if [ "$ext" = "docx" ] || [ "$ext" = "doc" ] || [ "$ext" = "wps" ] || [ "$ext" = "ofd" ]; then
        # 行政公文倾向，但不完全确定
        if head -30 "$file" 2>/dev/null | grep -qiE "制度|管理|办法|规定|流程|通知|行政|财务"; then
            echo "行政"; return
        fi
    fi

    # 再次：内容关键字
    if head -50 "$file" 2>/dev/null | grep -qiE "架构|接口|api|代码|部署|数据库|配置|系统|开发|算法|网络|安全|运维"; then
        echo "技术"; return
    fi
    if head -50 "$file" 2>/dev/null | grep -qiE "制度|管理|办法|规定|流程|规范|通知|行政|考勤|薪酬|人事|财务|合同"; then
        echo "行政"; return
    fi

    # 兜底
    echo "技术"
}

# 处理目标目录下散落文件
process_dir() {
    local dir="$1"; local count=0
    find "$dir" -maxdepth 1 -type f \( -iname "*.pdf" -o -iname "*.docx" -o -iname "*.doc" -o -iname "*.wps" -o -iname "*.ofd" -o -iname "*.md" -o -iname "*.txt" \) 2>/dev/null | while IFS= read -r file; do
        local cat; cat=$(sort_file "$file")
        mkdir -p "$dir/$cat"
        mv -f "$file" "$dir/$cat/" 2>/dev/null || true
        echo "  → $cat/$(basename "$file")"
    done
}

process_dir "$TARGET_DIR"

# 也处理日期子目录
find "$TARGET_DIR" -type d | while IFS= read -r dir; do
    if echo "$dir" | grep -qP '/\d{4}/\d{2}/\d{2}$'; then
        process_dir "$dir"
    fi
done

echo ""
echo -e "${GREEN}✅ 归类完成${NC}"
echo "=========================================="
