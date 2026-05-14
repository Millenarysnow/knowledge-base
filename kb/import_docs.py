from __future__ import annotations

import os
import re
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import category_keys, normalize_category, project_path
from .db import connect, insert_sign_record, sign_records_for_item, upsert_document
from .parser import SUPPORTED_EXT, parse_file
from .ollama import ollama_available, ollama_chat
from .util import (
    copy_file,
    file_sha256,
    first_value,
    markdown_escape,
    now_date_path,
    read_table,
    safe_filename,
    safe_markdown_name,
)

META_FILE_IDENTIFIER = ["文件标识", "file_identifier", "file_id", "id"]
META_TITLE = ["文件标题", "标题", "title"]
META_CATEGORY = ["文件类型", "文件分类", "分类", "category", "type"]
META_FILENAME = ["文件名", "filename", "file_name"]
META_ITEM_ID = ["文件事项ID", "事项id", "事项ID", "item_id"]
META_DOC_NUMBER = ["文件字号", "字号", "doc_number"]
META_SERIAL = ["文件流水号", "流水号", "serial_number"]

SIGN_ITEM_ID = ["事项id", "事项ID", "文件事项ID", "item_id"]
SIGN_SIGNER = ["签阅人", "查阅人", "姓名", "signer", "viewer"]
SIGN_TIME = ["签阅时间", "查阅时间", "时间", "sign_time", "view_time"]
SIGN_OPINION = ["签阅意见", "签阅内容", "查阅意见", "感受/笔记", "笔记", "领导批示", "opinion", "notes"]


def build_metadata_index(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """按文件名和文件标识建立索引。"""
    idx: Dict[str, Dict[str, str]] = {}
    for r in rows:
        filename = first_value(r, META_FILENAME)
        ident = first_value(r, META_FILE_IDENTIFIER)
        if filename:
            idx[filename.lower()] = r
            idx[Path(filename).name.lower()] = r
        if ident:
            idx[ident.lower()] = r
            idx[f"{ident.lower()}.pdf"] = r
            idx[f"{ident.lower()}.docx"] = r
            idx[f"{ident.lower()}.doc"] = r
            idx[f"{ident.lower()}.wps"] = r
            idx[f"{ident.lower()}.ofd"] = r
    return idx


def load_sign_records(rows: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    result: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        item_id = first_value(r, SIGN_ITEM_ID)
        signer = first_value(r, SIGN_SIGNER)
        if not item_id or not signer:
            continue
        result[item_id].append(
            {
                "item_id": item_id,
                "signer": signer,
                "sign_time": first_value(r, SIGN_TIME),
                "opinion": first_value(r, SIGN_OPINION),
            }
        )
    return result


def infer_date_from_path(source_root: Path, file_path: Path) -> str:
    try:
        parts = file_path.relative_to(source_root).parts
    except ValueError:
        return now_date_path()
    # 识别 2026/05/12 或 2026/5/12
    for i in range(0, max(len(parts) - 2, 0)):
        y, m, d = parts[i : i + 3]
        if re.fullmatch(r"\d{4}", y) and re.fullmatch(r"\d{1,2}", m) and re.fullmatch(r"\d{1,2}", d):
            return f"{int(y):04d}/{int(m):02d}/{int(d):02d}"
    return now_date_path()


def infer_category_from_dir(cfg: Dict[str, Any], source_root: Path, file_path: Path) -> Optional[str]:
    keys = set(category_keys(cfg))
    try:
        parts = file_path.relative_to(source_root).parts
    except ValueError:
        return None
    for part in parts[:-1]:
        if part in keys:
            return part
    return None


def infer_category_by_keywords(cfg: Dict[str, Any], file_path: Path, text_preview: str = "") -> Optional[str]:
    name = file_path.name.lower()
    hay = f"{name}\n{text_preview[:2000]}".lower()
    best_key = None
    best_score = 0
    for cat in cfg.get("categories", []) or []:
        key = cat.get("key")
        score = 0
        for kw in cat.get("keywords", []) or []:
            if str(kw).lower() in hay:
                score += 1
        if score > best_score:
            best_score = score
            best_key = key
    return best_key if best_score > 0 else None


def infer_category_by_ai(cfg: Dict[str, Any], title: str, text_preview: str) -> Optional[str]:
    """使用 Ollama 做兜底分类。失败时返回 None。"""
    models = cfg.get("models", {}) or {}
    base_url = os.environ.get("OLLAMA_BASE_URL", models.get("ollama_base_url", "http://localhost:11434"))
    model = os.environ.get("OLLAMA_MODEL", models.get("chat_model", "qwen2.5:7b"))
    if not ollama_available(base_url):
        return None
    cats = [c.get("key") for c in cfg.get("categories", []) or [] if c.get("key")]
    if not cats:
        return None
    prompt = f"""请判断文档属于哪个分类，只能从以下分类中选择一个：{', '.join(cats)}。

请只返回严格 JSON，例如：{{"category":"行政","reason":"简短理由"}}

文档标题：{title}
文档内容前 2000 字：
{text_preview[:2000]}
"""
    try:
        result = ollama_chat(
            base_url,
            model,
            prompt,
            system="你是中文企业文档分类助手，只返回 JSON，不输出多余内容。",
            timeout=120,
        )
        m = re.search(r"\{.*?\}", result, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
        cat = str(data.get("category", "")).strip()
        return normalize_category(cfg, cat) if cat in cats else None
    except Exception:
        return None


def find_source_files(source: Path) -> List[Path]:
    return sorted(
        [p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXT and not p.name.startswith("~")]
    )


def generate_markdown(
    doc: Dict[str, Any],
    body: str,
    sign_records: List[Dict[str, str]],
    source_download_path: str,
) -> str:
    lines: List[str] = []
    lines.append("---")
    for key in [
        "title",
        "category",
        "zone",
        "department",
        "file_identifier",
        "original_filename",
        "item_id",
        "doc_number",
        "serial_number",
        "stored_path",
    ]:
        val = doc.get(key)
        if val is not None and val != "":
            lines.append(f"{key}: {str(val).replace(chr(10), ' ')}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {doc['title']}")
    lines.append("")
    lines.append("## 文件信息")
    lines.append("")
    lines.append("| 字段 | 内容 |")
    lines.append("|---|---|")
    info_fields = [
        ("文件标题", doc.get("title")),
        ("文件类型", doc.get("category")),
        ("所属区域", "公共区" if doc.get("zone") == "public" else f"部门：{doc.get('department') or ''}"),
        ("文件标识", doc.get("file_identifier")),
        ("原始文件名", doc.get("original_filename")),
        ("文件事项ID", doc.get("item_id")),
        ("文件字号", doc.get("doc_number")),
        ("文件流水号", doc.get("serial_number")),
        ("来源文件", source_download_path),
    ]
    for k, v in info_fields:
        if v:
            lines.append(f"| {markdown_escape(k)} | {markdown_escape(v)} |")
    lines.append("")

    lines.append("## 签阅记录")
    lines.append("")
    if sign_records:
        lines.append("| 签阅人 | 签阅时间 | 签阅意见 |")
        lines.append("|---|---|---|")
        for r in sign_records:
            lines.append(
                f"| {markdown_escape(r.get('signer'))} | {markdown_escape(r.get('sign_time'))} | {markdown_escape(r.get('opinion'))} |"
            )
    else:
        lines.append("暂无签阅记录。")
    lines.append("")

    lines.append("## 正文")
    lines.append("")
    lines.append(body.strip() or "（未能解析出正文内容）")
    lines.append("")
    return "\n".join(lines)


def import_docs(
    cfg: Dict[str, Any],
    zone: str,
    source: str,
    dept: str | None = None,
    metadata: str | None = None,
    sign_records_path: str | None = None,
) -> Dict[str, Any]:
    zone = zone.strip()
    if zone not in {"public", "dept"}:
        raise ValueError("zone 必须是 public 或 dept")
    if zone == "dept" and not dept:
        raise ValueError("导入部门区时必须指定 --dept")

    source_root = Path(source).resolve()
    if not source_root.exists():
        raise FileNotFoundError(f"源目录不存在: {source_root}")

    meta_rows = read_table(metadata)
    meta_idx = build_metadata_index(meta_rows)
    sign_rows = read_table(sign_records_path)
    sign_map = load_sign_records(sign_rows)

    docs_root = project_path(cfg, "documents")
    raw_root = project_path(cfg, "raw")
    wiki_root = project_path(cfg, "wiki")

    zone_dir_name = "public" if zone == "public" else f"dept-{dept}"

    imported = 0
    failed: List[Tuple[str, str]] = []

    with connect(cfg) as conn:
        # 签阅记录先落库。与文件同批导入，但事项ID可能一对多。
        for item_id, records in sign_map.items():
            # 简化处理：同批重复导入会重复签阅记录；后续可加唯一约束。
            for r in records:
                insert_sign_record(conn, item_id, r["signer"], r.get("sign_time"), r.get("opinion"))

        for f in find_source_files(source_root):
            try:
                meta = meta_idx.get(f.name.lower()) or meta_idx.get(f.stem.lower()) or {}
                title = first_value(meta, META_TITLE) or f.stem
                file_identifier = first_value(meta, META_FILE_IDENTIFIER) or f.stem
                original_filename = first_value(meta, META_FILENAME) or f.name
                item_id = first_value(meta, META_ITEM_ID)
                doc_number = first_value(meta, META_DOC_NUMBER)
                serial_number = first_value(meta, META_SERIAL)

                # 分类优先级：元数据表 > 目录分类 > 文件名/内容关键词 > AI 分类 > 未分类。
                category = normalize_category(cfg, first_value(meta, META_CATEGORY))
                if not category:
                    category = infer_category_from_dir(cfg, source_root, f)

                # 为了分类关键词可能需要正文预览，但不想重复解析太多；这里先解析一次。
                body = parse_file(f)
                if not category:
                    category = infer_category_by_keywords(cfg, f, body)
                if not category:
                    category = infer_category_by_ai(cfg, title, body)
                if not category:
                    category = "未分类"

                date_path = infer_date_from_path(source_root, f)
                dest_dir = docs_root / zone_dir_name / date_path / category
                dest_file = dest_dir / safe_filename(original_filename or f.name)
                # 避免不同源文件同名覆盖。
                if dest_file.exists() and file_sha256(dest_file) != file_sha256(f):
                    dest_file = dest_dir / f"{f.stem}-{file_sha256(f)[:8]}{f.suffix}"
                copy_file(f, dest_file)

                checksum = file_sha256(dest_file)
                raw_rel = Path(zone_dir_name) / date_path / category / safe_markdown_name(title)
                wiki_rel = Path(zone_dir_name) / date_path / category / safe_markdown_name(title)
                raw_path = raw_root / raw_rel
                wiki_path = wiki_root / wiki_rel
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                wiki_path.parent.mkdir(parents=True, exist_ok=True)

                doc = {
                    "zone": zone,
                    "department": dept if zone == "dept" else None,
                    "file_identifier": file_identifier,
                    "title": title,
                    "category": category,
                    "original_filename": original_filename or f.name,
                    "stored_path": str(dest_file.relative_to(Path(cfg["_project_root"]))),
                    "raw_path": str(raw_path.relative_to(Path(cfg["_project_root"]))),
                    "wiki_path": str(wiki_path.relative_to(Path(cfg["_project_root"]))),
                    "item_id": item_id,
                    "doc_number": doc_number,
                    "serial_number": serial_number,
                    "checksum": checksum,
                }

                related_sign_records = sign_map.get(item_id, []) if item_id else []
                source_download = f"/files/{dest_file.relative_to(docs_root).as_posix()}"
                md = generate_markdown(doc, body, related_sign_records, source_download)
                raw_path.write_text(body, encoding="utf-8")
                wiki_path.write_text(md, encoding="utf-8")
                upsert_document(conn, doc)
                imported += 1
            except Exception as exc:
                failed.append((str(f), str(exc)))

        conn.commit()

    return {"imported": imported, "failed": failed}
