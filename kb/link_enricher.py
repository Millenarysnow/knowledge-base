from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from .config import project_path
from .db import connect, list_documents


def _document_url(doc_id: int) -> str:
    return f"/docs/{doc_id}"


def _download_url(doc_id: int) -> str:
    return f"/files/{doc_id}"


def enrich_wiki_links(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """向结构化 Markdown 追加 kb-web 文档详情/下载链接。

    AnythingLLM 的 citation 未必能直接跳转外部系统，因此至少把链接写进 Markdown，
    让 RAG 检索结果中包含可访问地址。kb-web 会对 /docs/{id} 和 /files/{id} 做权限控制。
    """
    project_root = Path(cfg["_project_root"])
    updated = 0
    skipped = 0
    marker = "<!-- kb-links -->"
    with connect(cfg) as conn:
        docs = list_documents(conn)
    for doc in docs:
        if not doc["wiki_path"]:
            skipped += 1
            continue
        path = project_root / doc["wiki_path"]
        if not path.exists():
            skipped += 1
            continue
        text = path.read_text(encoding="utf-8")
        block = f"""
{marker}

## 知识库链接

- 文档详情：{_document_url(int(doc['id']))}
- 原文件下载：{_download_url(int(doc['id']))}
"""
        if marker in text:
            before = text.split(marker, 1)[0].rstrip()
            new_text = before + "\n" + block.strip() + "\n"
        else:
            new_text = text.rstrip() + "\n\n" + block.strip() + "\n"
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            updated += 1
    return {"updated": updated, "skipped": skipped}
