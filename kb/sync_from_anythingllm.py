from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

from .config import project_path
from .db import connect, list_departments
from .import_docs import import_docs
from .util import file_sha256


SUPPORTED_SOURCE_EXT = {".pdf", ".docx", ".doc", ".wps", ".ofd", ".md", ".txt"}
DEFAULT_IGNORED_PARTS = {
    "vector-cache",
    "vectors",
    "lancedb",
    "chroma",
    "logs",
    "hotdir",
    "__MACOSX",
}
STATE_FILE = "data/db/sync-from-anythingllm-state.json"


def _safe_name(name: str) -> str:
    import re

    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip() or "untitled"


def _load_state(project_root: Path) -> Dict[str, Any]:
    path = project_root / STATE_FILE
    if not path.exists():
        return {"files": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"files": {}}


def _save_state(project_root: Path, state: Dict[str, Any]) -> None:
    path = project_root / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _iter_anythingllm_files(storage_root: Path) -> Iterable[Path]:
    """尽量从 AnythingLLM storage 中找原始/缓存文档。"""
    if not storage_root.exists():
        return []
    files: List[Path] = []
    for p in storage_root.rglob("*"):
        if not p.is_file():
            continue
        lowered_parts = {part.lower() for part in p.parts}
        if lowered_parts & DEFAULT_IGNORED_PARTS:
            continue
        if p.name.startswith(".") or p.name.startswith("~"):
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


def sync_from_anythingllm(
    cfg: Dict[str, Any],
    storage: str | None = None,
    default_dept: str | None = None,
    force: bool = False,
) -> Dict[str, Any]:
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

    state = _load_state(project_root)
    files_state: Dict[str, Any] = state.setdefault("files", {})

    grouped: Dict[str, List[Path]] = {}
    skipped: List[str] = []
    unchanged = 0
    scanned = 0
    for f in _iter_anythingllm_files(storage_root):
        scanned += 1
        dept = _guess_dept_from_path(f, dept_names, slug_to_dept) or default_dept
        if not dept:
            skipped.append(str(f))
            continue
        checksum = file_sha256(f)
        state_key = str(f.resolve())
        old = files_state.get(state_key, {})
        if not force and old.get("checksum") == checksum and old.get("dept") == dept:
            unchanged += 1
            continue
        grouped.setdefault(dept, []).append(f)
        files_state[state_key] = {"checksum": checksum, "dept": dept}

    imported = 0
    failed: List[Any] = []
    for dept, files in grouped.items():
        stage = temp_root / f"dept-{_safe_name(dept)}"
        stage.mkdir(parents=True, exist_ok=True)
        used_names: Set[str] = set()
        for f in files:
            dst = stage / f.name
            if dst.name in used_names or dst.exists():
                dst = stage / f"{f.stem}-{file_sha256(f)[:8]}{f.suffix}"
            used_names.add(dst.name)
            shutil.copy2(f, dst)
        res = import_docs(cfg, zone="dept", dept=dept, source=str(stage))
        imported += int(res.get("imported", 0))
        failed.extend(res.get("failed", []))

    _save_state(project_root, state)

    return {
        "storage": str(storage_root),
        "scanned": scanned,
        "unchanged": unchanged,
        "departments": {k: len(v) for k, v in grouped.items()},
        "imported": imported,
        "failed": failed,
        "skipped_without_dept": skipped[:50],
        "skipped_count": len(skipped),
        "note": "这是保守扫描实现；如 AnythingLLM API 提供文档列表/下载，后续应改为 API 精确同步。",
    }
