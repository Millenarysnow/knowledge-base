from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

from .db import connect, list_departments, list_documents


class AnythingLLMClient:
    """AnythingLLM API 客户端。

    AnythingLLM 同时存在 /api/* 和 /api/v1/* 两套常见路径。
    本客户端优先尝试 /api/v1，失败后回退到 /api。
    实际部署时仍应以实例 /api/docs 为准。
    """

    def __init__(self, cfg: Dict[str, Any]):
        if requests is None:
            raise RuntimeError("缺少 requests 依赖")
        acfg = cfg.get("anythingllm", {})
        self.base_url = os.environ.get("ANYTHINGLLM_BASE_URL", acfg.get("base_url", "http://localhost:3001")).rstrip("/")
        key_env = acfg.get("api_key_env", "ANYTHINGLLM_API_KEY")
        self.api_key = os.environ.get(key_env, "")
        if not self.api_key:
            raise RuntimeError(f"未设置 AnythingLLM API Key 环境变量: {key_env}")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def candidate_urls(self, path: str) -> List[str]:
        if not path.startswith("/"):
            path = "/" + path
        # path 传入不带 /api 或 /api/v1。
        return [self.base_url + "/api/v1" + path, self.base_url + "/api" + path]

    def request(self, method: str, path: str, **kwargs):
        errors: List[str] = []
        for url in self.candidate_urls(path):
            try:
                r = self.session.request(method, url, timeout=kwargs.pop("timeout", 300), **kwargs)
                if r.status_code in {404, 405}:
                    errors.append(f"{url}: {r.status_code}")
                    continue
                r.raise_for_status()
                if not r.text:
                    return {}
                try:
                    return r.json()
                except Exception:
                    return {"raw": r.text}
            except Exception as exc:
                errors.append(f"{url}: {exc}")
        raise RuntimeError("; ".join(errors))

    def get(self, path: str):
        return self.request("GET", path)

    def post(self, path: str, json=None, files=None, data=None):
        return self.request("POST", path, json=json, files=files, data=data)

    def ensure_workspace(self, name: str, slug: str) -> Dict[str, Any]:
        try:
            data = self.get("/workspaces")
            for w in data.get("workspaces", []):
                if w.get("slug") == slug:
                    return w
        except Exception:
            pass
        return self.post("/workspace/new", json={"name": name, "slug": slug})

    def list_users(self) -> List[Dict[str, Any]]:
        data = self.get("/admin/users")
        return data.get("users", []) if isinstance(data, dict) else []

    def ensure_user(self, username: str, password: str, role: str = "default") -> Optional[Dict[str, Any]]:
        """创建用户。若已存在则返回现有用户。

        AnythingLLM 角色常见值为 admin/default/manager。这里把 member 映射为 default。
        """
        role = "admin" if role == "admin" else "default"
        try:
            for u in self.list_users():
                if u.get("username") == username:
                    return u
        except Exception:
            pass
        data = self.post("/admin/users/new", json={"username": username, "password": password, "role": role})
        if isinstance(data, dict):
            return data.get("user") or data
        return None

    def assign_workspace_users(self, workspace_id: int, user_ids: List[int]) -> Dict[str, Any]:
        return self.post("/admin/workspace-users", json={"workspaceId": workspace_id, "userIds": user_ids})

    def upload_document(self, file_path: Path, folder_name: str | None = None) -> Dict[str, Any]:
        endpoint = "/document/upload" + (f"/{folder_name}" if folder_name else "")
        with file_path.open("rb") as f:
            return self.post(endpoint, files={"file": (file_path.name, f)})

    def upload_and_embed(self, workspace_slug: str, file_path: Path) -> Dict[str, Any]:
        endpoint = f"/workspace/{workspace_slug}/upload-and-embed"
        with file_path.open("rb") as f:
            return self.post(endpoint, files={"file": (file_path.name, f)})

    def update_embeddings(self, workspace_slug: str, adds: List[str], deletes: List[str] | None = None) -> Dict[str, Any]:
        return self.post(
            f"/workspace/{workspace_slug}/update-embeddings",
            json={"adds": adds, "deletes": deletes or []},
        )


def _extract_workspace_id(workspace_result: Any) -> Optional[int]:
    if not isinstance(workspace_result, dict):
        return None
    w = workspace_result.get("workspace") or workspace_result
    if isinstance(w, dict) and w.get("id") is not None:
        return int(w["id"])
    return None


def _extract_uploaded_ref(uploaded: Any, fallback_name: str) -> str:
    if isinstance(uploaded, dict):
        for key in ["location", "name", "docPath", "cached_filename"]:
            if uploaded.get(key):
                return uploaded[key]
        docs_arr = uploaded.get("documents") or uploaded.get("files") or []
        if docs_arr and isinstance(docs_arr[0], dict):
            return docs_arr[0].get("location") or docs_arr[0].get("name") or fallback_name
        doc = uploaded.get("document")
        if isinstance(doc, dict):
            return doc.get("location") or doc.get("name") or fallback_name
    return fallback_name


def sync_anythingllm(cfg: Dict[str, Any], sync_users: bool = True) -> Dict[str, Any]:
    """同步工作区、用户和文档。

    - 为每个部门创建 workspace。
    - 尝试创建用户并分配到对应 workspace。
    - 上传 wiki Markdown。
    - 公共文档加入所有部门 workspace，部门文档加入本部门 workspace。
    """
    client = AnythingLLMClient(cfg)
    project_root = Path(cfg["_project_root"])
    result = {"workspaces": 0, "users": 0, "uploaded": 0, "embedded": 0, "errors": []}
    with connect(cfg) as conn:
        depts = list_departments(conn)
        docs = list_documents(conn)
        workspace_by_dept: Dict[str, Dict[str, Any]] = {}

        for d in depts:
            try:
                ws = client.ensure_workspace(d["name"], d["slug"])
                workspace_by_dept[d["name"]] = ws
                result["workspaces"] += 1
            except Exception as exc:
                result["errors"].append(f"workspace {d['name']}: {exc}")

        if sync_users:
            rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
            # 先创建所有用户。
            users_by_dept: Dict[str, List[int]] = {}
            for u in rows:
                try:
                    user = client.ensure_user(u["username"], u["password"] or "kb123456", u["role"])
                    if user and user.get("id") is not None:
                        users_by_dept.setdefault(u["department"], []).append(int(user["id"]))
                        result["users"] += 1
                except Exception as exc:
                    result["errors"].append(f"user {u['username']}: {exc}")
            # 再分配 workspace。
            for dept_name, user_ids in users_by_dept.items():
                ws_id = _extract_workspace_id(workspace_by_dept.get(dept_name))
                if not ws_id or not user_ids:
                    continue
                try:
                    client.assign_workspace_users(ws_id, user_ids)
                except Exception as exc:
                    result["errors"].append(f"assign users {dept_name}: {exc}")

        doc_ref_by_id: Dict[int, str] = {}
        for doc in docs:
            try:
                wiki_path = project_root / doc["wiki_path"] if doc["wiki_path"] else None
                if not wiki_path or not wiki_path.exists():
                    continue
                uploaded = client.upload_document(wiki_path, folder_name="kb")
                result["uploaded"] += 1
                ref = _extract_uploaded_ref(uploaded, f"custom-documents/{wiki_path.name}")
                doc_ref_by_id[int(doc["id"])] = ref
            except Exception as exc:
                result["errors"].append(f"upload {doc['title']}: {exc}")

        slug_by_dept = {d["name"]: d["slug"] for d in depts}
        for dept_name, slug in slug_by_dept.items():
            adds: List[str] = []
            for doc in docs:
                if int(doc["id"]) not in doc_ref_by_id:
                    continue
                if doc["zone"] == "public" or doc["department"] == dept_name:
                    adds.append(doc_ref_by_id[int(doc["id"])])
            if not adds:
                continue
            try:
                client.update_embeddings(slug, adds)
                result["embedded"] += len(adds)
            except Exception as exc:
                result["errors"].append(f"embed {dept_name}: {exc}")

    return result
