#!/bin/bash
# ============================================
# 智能知识库 - 主控脚本
#
# 数据流向:
#   文档 → auto-sort (归类)
#        → doc-parser.py (解析 PDF/DOCX → raw/*.md)
#        → ai-classify.py (Ollama AI分类 → wiki/*.md)
#        → llmwiki build (编译静态站点)
#        → Nginx :80 + AnythingLLM :8301
#
# 用法:
#   ./compile-wiki.sh import <目录>                     # 全量导入
#   ./compile-wiki.sh import <目录> --dept <部门名>      # 导入到部门区
#   ./compile-wiki.sh build                             # 仅重新编译
#   ./compile-wiki.sh status                            # 查看状态
#   ./compile-wiki.sh import-records <查阅记录.csv>      # 导入文件查阅记录
# ============================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

DOCUMENTS_ROOT="$PROJECT_ROOT/volumes/documents"
RAW_DIR="$PROJECT_ROOT/volumes/llm-wiki-storage/raw"
WIKI_DIR="$PROJECT_ROOT/volumes/llm-wiki-storage/wiki"
SITE_DIR="$PROJECT_ROOT/volumes/llm-wiki-site"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()   { echo -e "${GREEN}[OK]${NC}  $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; }

usage() {
    cat << 'EOF'
智能知识库 — 主控工具

用法: compile-wiki.sh <命令> [参数]

命令:
  import <目录>                     批量导入到公共区
  import <目录> --dept <部门名>      批量导入到部门区
  build                             仅重新编译知识站点
  status                            查看运行状态与统计
  import-records <查阅记录.csv>      导入文件查阅记录（关联到知识库）

示例:
  ./compile-wiki.sh import /data/docs/
  ./compile-wiki.sh import /data/docs/ --dept 信息技术部
  ./compile-wiki.sh import-records ./view-records.csv
  ./compile-wiki.sh build
  ./compile-wiki.sh status
EOF
    exit 1
}

# ========== 工具函数 ==========
today_path() { date '+%Y/%m/%d'; }

check_deps() {
    if ! docker ps &>/dev/null 2>&1; then
        err "Docker 未运行"
        exit 1
    fi
    if ! docker ps 2>/dev/null | grep -q kb-ollama; then
        err "Ollama 服务未启动，请先运行: docker compose up -d"
        exit 1
    fi
}

sort_file_to_category() {
    local file="$1"
    local fname; fname=$(basename "$file")
    local fname_lower; fname_lower=$(echo "$fname" | tr '[:upper:]' '[:lower:]')

    # 会议类：文件名关键字
    if echo "$fname_lower" | grep -qE "会议|纪要|讨论|决议|复盘|例会|评审|座谈|研讨"; then
        echo "会议"; return
    fi
    # 报告类
    if echo "$fname_lower" | grep -qE "报告|总结|汇报|分析|调研|统计|年度|季度|月度|评估"; then
        echo "报告"; return
    fi
    # 行政类：扩展名
    local ext="${fname_lower##*.}"
    case "$ext" in
        docx|doc|wps|ofd) echo "行政"; return ;;
    esac
    # 行政类：内容关键字
    if head -50 "$file" 2>/dev/null | grep -qiE "制度|管理|办法|规定|流程|规范|通知|行政|考勤|薪酬|人事|财务|合同"; then
        echo "行政"; return
    fi
    # 技术类：内容关键字
    if head -50 "$file" 2>/dev/null | grep -qiE "架构|接口|api|代码|部署|数据库|配置|系统|开发|算法|网络|安全"; then
        echo "技术"; return
    fi
    echo "技术"
}

# ========== 步骤1: 文件组织 ==========
step_organize() {
    local src_dir="$1"; local zone_dir="$2"; local date_path
    date_path=$(today_path)
    log "步骤 1/4: 组织文件 → $zone_dir/$date_path/"

    [ ! -d "$src_dir" ] && { err "源目录不存在: $src_dir"; return 1; }

    local count=0
    while IFS= read -r file; do
        local category; category=$(sort_file_to_category "$file")
        local dest="$DOCUMENTS_ROOT/$zone_dir/$date_path/$category"
        mkdir -p "$dest"
        cp -f "$file" "$dest/" 2>/dev/null && count=$((count + 1))
        echo "  → $zone_dir/$date_path/$category/$(basename "$file")"
    done < <(find "$src_dir" -type f \( -iname "*.pdf" -o -iname "*.docx" -o -iname "*.doc" -o -iname "*.wps" -o -iname "*.ofd" -o -iname "*.md" -o -iname "*.txt" \) 2>/dev/null)

    ok "组织完成: $count 个文件"
}

# ========== 步骤2: 文档解析 ==========
step_parse() {
    log "步骤 2/4: 文档解析 (PDF/DOCX/OFD → raw/*.md)"
    if docker ps 2>/dev/null | grep -q kb-llmwiki; then
        docker exec kb-llmwiki bash -c "
            mkdir -p /app/storage/raw /app/storage/wiki /app/storage/db
            if [ -f /app/scripts/doc-parser.py ]; then
                python3 /app/scripts/doc-parser.py /app/documents /app/storage/raw --cache-dir /app/storage/db
            else
                echo 'WARN: doc-parser.py 未找到'
            fi
        " 2>&1
    else
        warn "llmwiki 容器未运行"
    fi
    local n; n=$(find "$RAW_DIR" -name "*.md" -type f 2>/dev/null | wc -l)
    ok "文档解析完成: $n 篇"
}

# ========== 步骤3: AI 分类 ==========
step_classify() {
    log "步骤 3/4: AI 分类 (raw → wiki，调用 Ollama)"
    if docker ps 2>/dev/null | grep -q kb-llmwiki; then
        docker exec kb-llmwiki bash -c "
            mkdir -p /app/storage/wiki
            if [ -f /app/scripts/ai-classify.py ]; then
                python3 /app/scripts/ai-classify.py --input /app/storage/raw --output /app/storage/wiki
            else
                echo 'WARN: ai-classify.py 未找到，跳过AI分类'
            fi
        " 2>&1
    else
        warn "llmwiki 容器未运行"
    fi
    local n; n=$(find "$WIKI_DIR" -name "*.md" -type f 2>/dev/null | wc -l)
    ok "AI 分类完成: $n 个结构化条目"
}

# ========== 步骤4: LLM Wiki 编译 ==========
step_build() {
    log "步骤 4/4: LLM Wiki 编译站点"
    if docker ps 2>/dev/null | grep -q kb-llmwiki; then
        docker exec kb-llmwiki bash -c "
            cd /app/storage
            if command -v llmwiki &>/dev/null; then
                llmwiki build --raw wiki --site /app/site 2>&1 || true
            fi
        " 2>&1
    fi
    local n; n=$(find "$SITE_DIR" -name "*.html" -type f 2>/dev/null | wc -l)
    ok "静态站点生成: $n 页"
}

# ========== 查阅记录导入 ==========
do_import_records() {
    local csv_file="${1:?请指定CSV文件路径}"
    [ ! -f "$csv_file" ] && { err "文件不存在: $csv_file"; exit 1; }

    log "导入查阅记录: $csv_file"

    local tmp="/tmp/view-records-import.csv"
    cp "$csv_file" "$tmp"
    docker cp "$tmp" kb-llmwiki:/tmp/view-records.csv 2>/dev/null || true
    rm -f "$tmp"

    if docker ps 2>/dev/null | grep -q kb-llmwiki; then
        docker exec kb-llmwiki bash -c "
            if [ -f /app/scripts/import-view-records.py ]; then
                python3 /app/scripts/import-view-records.py --csv /tmp/view-records.csv --wiki-dir /app/storage/wiki
            else
                echo 'WARN: import-view-records.py 未找到'
            fi
        " 2>&1
    fi

    ok "查阅记录导入完成"
    step_build
}

# ========== 导入 ==========
do_import() {
    local src="$1"; local zone="public"; shift || true
    while [ $# -gt 0 ]; do
        case "$1" in
            --dept) zone="dept-$2"; shift 2 ;;
            *) shift ;;
        esac
    done

    [ "$zone" != "public" ] && mkdir -p "$DOCUMENTS_ROOT/$zone"

    echo ""; echo "=========================================="
    echo "  智能知识库 — 批量导入"; echo "  区域: $zone"; echo "  日期: $(today_path)"
    echo "=========================================="; echo ""

    step_organize "$src" "$zone"
    echo ""; step_parse
    echo ""; step_classify
    echo ""; step_build
    echo ""; print_summary
}

# ========== 仅编译 ==========
do_build() {
    echo "=========================================="
    echo "  智能知识库 — 重新编译"
    echo "=========================================="; echo ""
    step_parse; echo ""; step_classify; echo ""; step_build
    echo ""; print_summary
}

# ========== 状态 ==========
print_summary() {
    local total parsed wiki html
    total=$(find "$DOCUMENTS_ROOT" -type f \( -iname "*.pdf" -o -iname "*.docx" -o -iname "*.doc" -o -iname "*.wps" -o -iname "*.ofd" -o -iname "*.md" -o -iname "*.txt" \) 2>/dev/null | wc -l)
    parsed=$(find "$RAW_DIR" -name "*.md" -type f 2>/dev/null | wc -l)
    wiki=$(find "$WIKI_DIR" -name "*.md" -type f 2>/dev/null | wc -l)
    html=$(find "$SITE_DIR" -name "*.html" -type f 2>/dev/null | wc -l)
    echo ""; echo "=========================================="
    echo "  知识库状态"
    echo "=========================================="
    echo "  源文档:    $total 个"
    echo "  已解析:    $parsed 篇"
    echo "  结构化:    $wiki 条"
    echo "  静态页面:  $html 页"
    echo ""
    echo "  结构化浏览: http://localhost"
    echo "  智能问答:   http://localhost:8301"
    echo "  部门上传:   http://localhost:8888/upload"
    echo "=========================================="
}

do_status() {
    print_summary
    echo ""; echo "--- 服务健康 ---"
    curl -s "http://localhost:11434/api/tags" >/dev/null 2>&1 && echo "  Ollama :11434       ✅" || echo "  Ollama :11434       ❌"
    curl -s "http://localhost:8301" >/dev/null 2>&1 && echo "  AnythingLLM :8301   ✅" || echo "  AnythingLLM :8301   ❌"
    curl -s "http://localhost:80/health" >/dev/null 2>&1 && echo "  Nginx :80           ✅" || echo "  Nginx :80           ❌"
    curl -s "http://localhost:8888" >/dev/null 2>&1 && echo "  Upload :8888        ✅" || echo "  Upload :8888        ❌"
    echo ""
}

# ========== 入口 ==========
check_deps
MODE="${1:-}"
case "$MODE" in
    import)
        [ $# -lt 2 ] && usage
        src_dir="$2"; shift 2
        do_import "$src_dir" "$@"
        ;;
    build)        do_build ;;
    status)       do_status ;;
    import-records) do_import_records "${2:-}" ;;
    *)            usage ;;
esac
