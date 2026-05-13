from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List

from .config import project_path
from .db import connect, list_departments, list_documents, sign_records_for_item

try:
    import markdown
except Exception:  # pragma: no cover
    markdown = None


BASE_CSS = """
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif;background:#f6f7fb;color:#1f2937}
header{background:#0f172a;color:#fff;padding:18px 32px;display:flex;align-items:center;justify-content:space-between}
header a{color:#bfdbfe;text-decoration:none;margin-left:16px}
main{max-width:1180px;margin:0 auto;padding:24px}
.card{background:white;border:1px solid #e5e7eb;border-radius:10px;padding:18px;margin:14px 0;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}.muted{color:#6b7280}.tag{display:inline-block;background:#e0f2fe;color:#0369a1;padding:2px 8px;border-radius:999px;font-size:12px;margin-right:6px}.warn{background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;padding:12px;border-radius:8px}.table{width:100%;border-collapse:collapse}.table th,.table td{border-bottom:1px solid #e5e7eb;text-align:left;padding:9px}.table th{background:#f8fafc}a{color:#2563eb}.doc-body{line-height:1.75}.doc-body table{border-collapse:collapse;width:100%;margin:12px 0}.doc-body th,.doc-body td{border:1px solid #e5e7eb;padding:6px 8px}.doc-body th{background:#f8fafc}
"""


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def page(title: str, body: str, cfg: Dict[str, Any]) -> str:
    auth_note = ""
    if cfg.get("site", {}).get("enable_auth_note", True):
        auth_note = '<div class="warn">权限提示：普通用户只能查看公共区和本部门文档；管理员可查看全部。当前静态站点需由前置认证/反向代理控制访问。</div>'
    return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><link rel="stylesheet" href="/assets/style.css"></head>
<body><header><div><strong>{html.escape(cfg.get('app',{}).get('name','智能知识库'))}</strong></div><nav><a href="/index.html">首页</a><a href="/documents.html">文档</a><a href="/graph.html">知识图谱</a></nav></header><main>{auth_note}{body}</main></body></html>"""


def md_to_html(text: str) -> str:
    if markdown is None:
        return "<pre>" + html.escape(text) + "</pre>"
    return markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])


def doc_url(doc_id: int) -> str:
    return f"/docs/{doc_id}.html"


def build_site(cfg: Dict[str, Any]) -> Dict[str, Any]:
    site = project_path(cfg, "site")
    docs_root = project_path(cfg, "documents")
    if site.exists():
        shutil.rmtree(site)
    (site / "assets").mkdir(parents=True, exist_ok=True)
    write(site / "assets" / "style.css", BASE_CSS)

    with connect(cfg) as conn:
        departments = list_departments(conn)
        documents = list_documents(conn)

        cards = []
        cards.append(f"<div class='card'><h2>统计</h2><p>部门数：{len(departments)}；文档数：{len(documents)}</p></div>")
        cards.append("<div class='card'><h2>部门</h2><div class='grid'>" + "".join(
            f"<div class='card'><h3>{html.escape(d['name'])}</h3><p class='muted'>workspace: {html.escape(d['slug'])}</p></div>"
            for d in departments
        ) + "</div></div>")
        write(site / "index.html", page("智能知识库", "\n".join(cards), cfg))

        rows = []
        for d in documents:
            zone = "公共区" if d["zone"] == "public" else f"部门：{d['department']}"
            rows.append(
                f"<tr><td><a href='{doc_url(d['id'])}'>{html.escape(d['title'])}</a></td><td>{html.escape(d['category'] or '')}</td><td>{html.escape(zone)}</td><td>{html.escape(d['doc_number'] or '')}</td><td>{html.escape(d['item_id'] or '')}</td></tr>"
            )
        body = "<div class='card'><h1>文档列表</h1><table class='table'><thead><tr><th>标题</th><th>分类</th><th>区域</th><th>字号</th><th>事项ID</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        write(site / "documents.html", page("文档列表", body, cfg))

        graph_nodes = []
        graph_edges = []
        item_to_docs: Dict[str, List[Any]] = {}
        for d in documents:
            item = d["item_id"]
            if item:
                item_to_docs.setdefault(item, []).append(d)
        for d in documents:
            graph_nodes.append({"id": f"doc-{d['id']}", "label": d["title"], "url": doc_url(d["id"])})
        for item, ds in item_to_docs.items():
            graph_nodes.append({"id": f"item-{item}", "label": f"事项 {item}"})
            for d in ds:
                graph_edges.append({"from": f"item-{item}", "to": f"doc-{d['id']}"})
        graph_html = f"""
<div class='card'><h1>知识图谱</h1><p class='muted'>MVP 图谱：事项ID ↔ 文档。</p><pre>{html.escape(json.dumps({'nodes': graph_nodes, 'edges': graph_edges}, ensure_ascii=False, indent=2))}</pre></div>
"""
        write(site / "graph.html", page("知识图谱", graph_html, cfg))

        for d in documents:
            wiki_path = Path(cfg["_project_root"]) / d["wiki_path"] if d["wiki_path"] else None
            if wiki_path and wiki_path.exists():
                md = wiki_path.read_text(encoding="utf-8")
            else:
                md = f"# {d['title']}\n\n（未生成结构化内容）"
            content = md_to_html(md)
            source_link = ""
            stored = Path(cfg["_project_root"]) / d["stored_path"]
            try:
                rel_to_docs = stored.relative_to(docs_root).as_posix()
                source_link = f"<p><a href='/files/{html.escape(rel_to_docs)}'>下载原文件</a></p>"
            except Exception:
                pass
            body = f"<div class='card'><a href='/documents.html'>← 返回文档列表</a><div class='doc-body'>{content}</div>{source_link}</div>"
            write(site / "docs" / f"{d['id']}.html", page(d["title"], body, cfg))

        # 搜索索引
        index = [
            {
                "id": d["id"],
                "title": d["title"],
                "category": d["category"],
                "zone": d["zone"],
                "department": d["department"],
                "item_id": d["item_id"],
                "doc_number": d["doc_number"],
                "url": doc_url(d["id"]),
            }
            for d in documents
        ]
        write(site / "search-index.json", json.dumps(index, ensure_ascii=False, indent=2))

    return {"site": str(site), "documents": len(documents)}
