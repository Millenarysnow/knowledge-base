#!/bin/bash
# ============================================
# 智能知识库 - 批量导入部门和用户
# 支持格式: CSV / Excel (.xlsx)
#
# CSV格式:
#   type,dept_name,username,password,role
#   dept,研发部,,,
#   user,研发部,zhangsan,pass123,admin
#   user,研发部,lisi,pass456,member
#
# Excel格式（同上，.xlsx/.xls）:
#   type    | dept_name | username | password | role
#   dept    | 研发部    |          |          |
#   user    | 研发部    | zhangsan | pass123  | admin
# ============================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
USERS_DIR="$PROJECT_ROOT/volumes/users"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

if [ $# -lt 1 ]; then
    echo "用法: $0 <CSV或Excel文件>"
    echo ""
    echo "CSV格式示例:"
    echo "  type,dept_name,username,password,role"
    echo "  dept,研发部,,,"
    echo "  user,研发部,zhangsan,pass123,admin"
    echo "  user,研发部,lisi,pass456,member"
    echo "  dept,财务部,,,"
    echo "  user,财务部,wangwu,pass789,admin"
    exit 1
fi

INPUT_FILE="$1"

if [ ! -f "$INPUT_FILE" ]; then
    echo -e "${RED}错误: 文件不存在: $INPUT_FILE${NC}"
    exit 1
fi

mkdir -p "$USERS_DIR"

echo "=========================================="
echo "  智能知识库 - 批量导入部门和用户"
echo "=========================================="
echo ""

# ---------- 解析函数 ----------
parse_csv() {
    local file="$1"
    local dept_count=0 user_count=0
    local current_dept=""

    # 跳过表头
    tail -n +2 "$file" | while IFS=',' read -r type dept_name username password role; do
        # 去除首尾空格
        type=$(echo "$type" | xargs)
        dept_name=$(echo "$dept_name" | xargs)
        username=$(echo "$username" | xargs)
        password=$(echo "$password" | xargs)
        role=$(echo "$role" | xargs)

        [ -z "$type" ] && continue

        if [ "$type" = "dept" ]; then
            handle_dept "$dept_name"
        elif [ "$type" = "user" ]; then
            handle_user "$dept_name" "$username" "$password" "$role"
        fi
    done
}

handle_dept() {
    local name="$1"
    [ -z "$name" ] && return

    local dept_dir="$PROJECT_ROOT/volumes/documents/dept-$name"

    if [ -d "$dept_dir" ]; then
        echo -e "  ${YELLOW}⚠ 部门已存在: $name${NC}"
    else
        mkdir -p "$dept_dir"
        echo -e "  ${GREEN}✅ 创建部门: $name${NC}"
        echo -e "     目录: volumes/documents/dept-$name/"
    fi

    # 写入部门记录
    if [ ! -f "$USERS_DIR/depts.csv" ]; then
        echo "dept_name,created_at" > "$USERS_DIR/depts.csv"
    fi
    if ! grep -q "^${name}," "$USERS_DIR/depts.csv" 2>/dev/null; then
        echo "$name,$(date '+%Y-%m-%d %H:%M:%S')" >> "$USERS_DIR/depts.csv"
    fi
}

handle_user() {
    local dept="$1" user="$2" pass="$3" role="$4"
    [ -z "$dept" ] && return
    [ -z "$user" ] && return
    [ -z "$pass" ] && pass="kb123456"
    [ -z "$role" ] && role="member"

    # 确保部门存在
    local dept_dir="$PROJECT_ROOT/volumes/documents/dept-$dept"
    if [ ! -d "$dept_dir" ]; then
        mkdir -p "$dept_dir"
        echo -e "  ${GREEN}✅ 自动创建部门: $dept${NC}"
    fi

    # 写入用户记录
    if [ ! -f "$USERS_DIR/users.csv" ]; then
        echo "dept,username,password,role,created_at" > "$USERS_DIR/users.csv"
    fi

    if grep -q "^${dept},${user}," "$USERS_DIR/users.csv" 2>/dev/null; then
        echo -e "  ${YELLOW}⚠ 用户已存在: $dept/$user${NC}"
    else
        echo "$dept,$user,$pass,$role,$(date '+%Y-%m-%d %H:%M:%S')" >> "$USERS_DIR/users.csv"
        echo -e "  ${GREEN}✅ 用户: $dept / $user (角色: $role)${NC}"
    fi
}

# ---------- 主逻辑 ----------
EXT="${INPUT_FILE##*.}"
case "$EXT" in
    csv)
        echo "[模式] CSV 导入"
        parse_csv "$INPUT_FILE"
        ;;
    xlsx|xls)
        echo "[模式] Excel 导入"
        # 使用 Python 解析 Excel 并转为 CSV 处理
        python3 -c "
import sys, csv
try:
    import openpyxl
    wb = openpyxl.load_workbook('$INPUT_FILE')
    ws = wb.active
    writer = csv.writer(sys.stdout)
    for row in ws.iter_rows(values_only=True):
        writer.writerow([str(c) if c is not None else '' for c in row])
except ImportError:
    print('ERROR: 需要安装 openpyxl: pip install openpyxl', file=sys.stderr)
    sys.exit(1)
" > "$USERS_DIR/_temp_import.csv" 2>/dev/null

        if [ $? -eq 0 ] && [ -s "$USERS_DIR/_temp_import.csv" ]; then
            parse_csv "$USERS_DIR/_temp_import.csv"
            rm -f "$USERS_DIR/_temp_import.csv"
        else
            echo -e "${RED}错误: Excel 解析失败，请安装 openpyxl 或使用 CSV 格式${NC}"
            exit 1
        fi
        ;;
    *)
        echo -e "${RED}错误: 不支持的文件格式: $EXT（仅支持 .csv / .xlsx / .xls）${NC}"
        exit 1
        ;;
esac

# ---------- 输出汇总 ----------
echo ""
echo "=========================================="
echo "  导入完成"
echo "=========================================="
echo "  部门数: $(tail -n +2 "$USERS_DIR/depts.csv" 2>/dev/null | wc -l || echo 0)"
echo "  用户数: $(tail -n +2 "$USERS_DIR/users.csv" 2>/dev/null | wc -l || echo 0)"
echo ""
echo "  部门列表:"
tail -n +2 "$USERS_DIR/depts.csv" 2>/dev/null | while IFS=',' read -r name created; do
    echo "    📂 $name"
done || true
echo ""
echo "  用户列表:"
tail -n +2 "$USERS_DIR/users.csv" 2>/dev/null | while IFS=',' read -r dept user pass role created; do
    echo "    👤 $dept / $user ($role)"
done || true
echo "=========================================="
