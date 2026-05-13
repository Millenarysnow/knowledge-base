from __future__ import annotations

import csv
import hashlib
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def now_date_path() -> str:
    return datetime.now().strftime("%Y/%m/%d")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip() or "untitled"


def safe_markdown_name(name: str) -> str:
    base = safe_filename(name)
    if not base.lower().endswith(".md"):
        base += ".md"
    return base


def read_table(path: str | os.PathLike[str] | None) -> List[Dict[str, str]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"表格文件不存在: {p}")
    ext = p.suffix.lower()
    if ext == ".csv":
        return read_csv(p)
    if ext in {".xlsx", ".xls"}:
        return read_excel(p)
    raise ValueError(f"不支持的表格格式: {p.suffix}")


def read_csv(path: Path) -> List[Dict[str, str]]:
    for encoding in ["utf-8-sig", "utf-8", "gbk"]:
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                return [normalize_row(r) for r in reader]
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 0, f"无法识别 CSV 编码: {path}")


def read_excel(path: Path) -> List[Dict[str, str]]:
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("读取 Excel 需要 openpyxl，请安装依赖") from exc
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    result: List[Dict[str, str]] = []
    for row in rows[1:]:
        d: Dict[str, str] = {}
        for i, h in enumerate(headers):
            if not h:
                continue
            val = row[i] if i < len(row) else ""
            d[h] = "" if val is None else str(val).strip()
        if any(v for v in d.values()):
            result.append(normalize_row(d))
    return result


def normalize_row(row: Dict[str, Any]) -> Dict[str, str]:
    return {str(k).strip(): "" if v is None else str(v).strip() for k, v in row.items()}


def first_value(row: Dict[str, str], names: Iterable[str]) -> str:
    for n in names:
        if n in row and row[n].strip():
            return row[n].strip()
    return ""


def markdown_escape(text: Any) -> str:
    s = "" if text is None else str(text)
    return s.replace("|", "\\|").replace("\n", "<br>")


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
