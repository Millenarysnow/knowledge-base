from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("缺少依赖 PyYAML，请执行 pip install -r requirements.txt") from exc


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


def load_config(path: str | os.PathLike[str] | None = None) -> Dict[str, Any]:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not cfg_path.is_absolute():
        cfg_path = PROJECT_ROOT / cfg_path
    if not cfg_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg["_config_path"] = str(cfg_path)
    cfg["_project_root"] = str(PROJECT_ROOT)
    return cfg


def project_path(cfg: Dict[str, Any], key: str) -> Path:
    raw = cfg.get("paths", {}).get(key)
    if not raw:
        raise KeyError(f"配置 paths.{key} 不存在")
    p = Path(raw)
    if not p.is_absolute():
        p = Path(cfg["_project_root"]) / p
    return p


def ensure_dirs(cfg: Dict[str, Any]) -> None:
    for key in ["documents", "raw", "wiki", "site"]:
        project_path(cfg, key).mkdir(parents=True, exist_ok=True)
    project_path(cfg, "db").parent.mkdir(parents=True, exist_ok=True)


def categories(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(cfg.get("categories", []) or [])


def category_keys(cfg: Dict[str, Any]) -> List[str]:
    return [c.get("key") for c in categories(cfg) if c.get("key")]


def normalize_category(cfg: Dict[str, Any], value: str | None) -> str | None:
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    for c in categories(cfg):
        if v == c.get("key") or v == c.get("label"):
            return c.get("key")
    return v


def dept_slug(name: str) -> str:
    """AnythingLLM workspace slug。中文 slug 在部分系统中可能不可用，采用稳定 ASCII。"""
    import hashlib

    digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    return f"dept-{digest}"
