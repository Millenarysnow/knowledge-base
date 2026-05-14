from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .config import project_path
from .db import connect, list_departments
from .import_docs import import_docs


SUPPORTED_SOURCE_EXT = {".pdf", ".docx", ".doc", ".wps", ".ofd", ".md", ".txt"}


def _safe_name(name: str) -> str:
    import re

    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip() or "untitled"


def _iter_anythingllm_files(storage_root: Path) -> Iterable[Path]:
    """尽量从 AnythingLLM storage 中找原始/缓存文档。

    AnythingLLM 版本间目录差异较大，所以这里只做保守扫描：
    - 跳过 vector db / sqlite / json 元数据。
    - 只收集常见文档扩展名。
    """
    if not storage_root.exists():
        return []
    ignored_parts = {"vector-cache", "vectors", "lancedb", "chroma", "logs"}
    files: List[Path] = []
    for p in storage_root.rglob("*"):
        if not p.is_file():
            continue
        if any(part.lower() in ignored_parts for part in p.parts):
            continue
        if p.suffix.lower() in SUPPORTED_SOURCE_EXT:
            files.append(p)
    return files


def _guess_dept_from_path(path: Path, dept_names: List[str], slug_to_dept: Dict[str, str]) -> str | None:
    hay = "/".join(path.parts)
    for dept in dept_names:
        if dept in hay:
            return dept
    for slug, dept in slug_to_dept.items():
        if slug in hay:
            return dept
    return None


def sync_from_anythingllm(cfg: Dict[str, Any], storage: str | None = None, default_dept: str | None = None) -> Dict[str, Any]:
    """从 AnythingLLM 本地存储目录保守扫描用户上传文件，并导入本地知识库。

    这是在无法确定 AnythingLLM API/存储结构前的兜底实现。
    实际部署时建议先观察 data/anythingllm 目录结构，再根据情况增加更精确的 workspace 映射。
    """
    project_root = Path(cfg["_project_root"])
    storage_root = Path(storage) if storage else project_root / "data" / "anythingllm"
    if not storage_root.is_absolute():
        storage_root = project_root / storage_root

    temp_root = project_root / "data" / "_sync_from_anythingllm"
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True, exist_ok=True)

    with connect(cfg) as conn:
        depts = list_departments(conn)
    dept_names = [d["name"] for d in depts]
    slug_to_dept = {d["slug"]: d["name"] for d in depts}

    grouped: Dict[str, List[Path]] = {}
    skipped: List[str] = []
    for f in _iter_anythingllm_files(storage_root):
        dept = _guess_dept_from_path(f, dept_names, slug_to_dept) or default_dept
        if not dept:
            skipped.append(str(f))
            continue
        grouped.setdefault(dept, []).append(f)

    imported = 0
    failed: List[Any] = []
    for dept, files in grouped.items():
        stage = temp_root / f"dept-{_safe_name(dept)}"
        stage.mkdir(parents=True, exist_ok=True)
        for f in files:
            dst = stage / f.name
            if dst.exists():
                dst = stage / f"{f.stem}-{abs(hash(str(f))) % 100000}{f.suffix}"
            shutil.copy2(f, dst)
        res = import_docs(cfg, zone="dept", dept=dept, source=str(stage))
        imported += int(res.get("imported", 0))
        failed.extend(res.get("failed", []))

    return {
        "storage": str(storage_root),
        "departments": {k: len(v) for k, v in grouped.items()},
        "imported": imported,
        "failed": failed,
        "skipped_without_dept": skipped[:50],
        "skipped_count": len(skipped),
        "note": "这是保守扫描实现；如 AnythingLLM API 提供文档列表/下载，后续应改为 API 精确同步。",
    }
