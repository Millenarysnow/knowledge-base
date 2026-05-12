#!/usr/bin/env python3
"""
智能知识库 - 文件查阅记录导入
解析查阅记录 CSV，匹配 wiki/ 目录下的文件，将查阅记录注入文档元数据

CSV 格式（列名支持中英文）:
    文件名称,查阅人,查阅时间,感受/笔记,是否处理,领导批示,备注

用法:
    python3 import-view-records.py --csv <查阅记录.csv> --wiki-dir <wiki目录>
"""
import os, sys, csv, json, re, argparse
from collections import defaultdict
from datetime import datetime


def find_wiki_file(filename, wiki_dir):
    """按文件名模糊匹配 wiki 目录下的 .md 文件"""
    name_no_ext = os.path.splitext(filename)[0].lower()
    for root, dirs, files in os.walk(wiki_dir):
        for f in sorted(files):
            if not f.endswith(".md"):
                continue
            f_lower = f.lower()
            if name_no_ext in f_lower or f_lower.startswith(name_no_ext):
                return os.path.join(root, f)
    return None


def normalize_row(row):
    """支持中英文列名"""
    mapping = {
        "文件名称": "filename", "文件名": "filename", "file": "filename",
        "查阅人": "viewer", "姓名": "viewer", "viewer": "viewer",
        "查阅时间": "view_time", "时间": "view_time", "time": "view_time", "date": "view_time",
        "感受/笔记": "notes", "感受": "notes", "笔记": "notes", "notes": "notes",
        "领导批示": "leader_comment", "批示": "leader_comment", "领导意见": "leader_comment",
        "是否处理": "processed", "processed": "processed",
        "备注": "remark", "remark": "remark",
    }
    result = {}
    for k, v in row.items():
        k_clean = k.strip()
        key = mapping.get(k_clean, k_clean)
        result[key] = v.strip() if v else ""
    return result


def main():
    ap = argparse.ArgumentParser(description="文件查阅记录导入")
    ap.add_argument("--csv", required=True, help="查阅记录CSV文件路径")
    ap.add_argument("--wiki-dir", default="/app/storage/wiki", help="wiki目录路径")
    args = ap.parse_args()

    if not os.path.isfile(args.csv):
        print(f"错误: CSV文件不存在: {args.csv}")
        sys.exit(1)

    # 解析CSV，按文件名分组
    records = defaultdict(list)
    with open(args.csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            r = normalize_row(row)
            fname = r.get("filename", "")
            if fname:
                records[fname].append(r)

    print("=" * 55)
    print("  智能知识库 - 查阅记录导入")
    print(f"  CSV: {args.csv}")
    print(f"  目标: {args.wiki_dir}")
    print("=" * 55)

    linked = 0
    unmatched = []

    for filename, recs in records.items():
        wiki_path = find_wiki_file(filename, args.wiki_dir)
        if not wiki_path:
            unmatched.append(filename)
            print(f"  ⚠ 未匹配: {filename}")
            continue

        # 读取现有 wiki 文件
        with open(wiki_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 定位 frontmatter 结束
        fm_end = 0
        m = re.match(r'^---\s*\n.*?\n---\s*\n', content, re.DOTALL)
        if m:
            fm_end = m.end()

        # 收集领导批示到元数据
        leader_comments = [
            r["leader_comment"]
            for r in recs
            if r.get("leader_comment") and r["leader_comment"] not in ("", "-", "无")
        ]
        if leader_comments:
            meta_line = f"leader_comments: {json.dumps(leader_comments, ensure_ascii=False)}\n"
            if fm_end > 0:
                content = content[:fm_end] + meta_line + content[fm_end:]

        # 构造查阅记录表格
        table = "\n\n## 文件查阅记录\n\n"
        table += "| 查阅人 | 时间 | 笔记/感受 | 领导批示 | 状态 |\n"
        table += "|--------|------|-----------|----------|------|\n"
        for r in recs:
            table += (
                f"| {r.get('viewer', '')} "
                f"| {r.get('view_time', '')} "
                f"| {r.get('notes', '')} "
                f"| {r.get('leader_comment', '')} "
                f"| {r.get('processed', '')} |\n"
            )

        with open(wiki_path, "w", encoding="utf-8") as f:
            f.write(content + table)

        linked += 1
        print(f"  ✅ {filename} → {os.path.basename(wiki_path)} ({len(recs)}条记录)")

    print("-" * 55)
    print(f"  关联成功: {linked} 个文件")
    if unmatched:
        print(f"  未匹配:   {len(unmatched)} 个文件")
        for u in unmatched:
            print(f"    - {u}")
    print("=" * 55)
    return 0 if not unmatched else 1


if __name__ == "__main__":
    sys.exit(main())
