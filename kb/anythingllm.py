from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

from .db import (
    connect,
    list_departments,
    list_documents,
    log_sync,
    mark_document_synced,
    mark_document_uploaded,
    mark_workspace_document,
)


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
        configured_base = os.environ.get("ANYTHINGLLM_BASE_URL", acfg.get("base_url", "http://localhost:8301")).rstrip("/")
        self.base_urls = self._candidate_base_urls(configured_base)
        key_env = acfg.get("api_key_env", "ANYTHINGLLM_API_KEY")
        self.api_key = os.environ.get(key_env, "").strip()
        if not self.api_key:
            raise RuntimeError(
                f"未设置 AnythingLLM API Key 环境变量: {key_env}。\n"
                f"  - 宿主机执行：在 .env 中写入 {key_env}=xxx 后重新打开终端，或 export {key_env}=xxx；\n"
                f"  - 容器内执行：修改 .env 后必须 `docker compose restart kb-worker kb-web` 让新 .env 生效。"
            )
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})
        self.verbose = os.environ.get("KB_VERBOSE", "").lower() in {"1", "true", "yes"}
        self.last_attempts: List[str] = []

    @staticmethod
    def _candidate_base_urls(base_url: str) -> List[str]:
        """生成候选 AnythingLLM 基地址。

        - 宿主机直接执行 CLI 时通常应访问 http://localhost:8301。
        - docker compose 容器内执行时通常应访问 http://anythingllm:3001。
        为降低使用门槛，这里自动增加互补 fallback。
        """
        urls = [base_url.rstrip("/")]
        if "anythingllm" in base_url:
            urls.append("http://localhost:8301")
            urls.append("http://127.0.0.1:8301")
        if "localhost" in base_url or "127.0.0.1" in base_url:
            urls.append("http://anythingllm:3001")
        out: List[str] = []
        for u in urls:
            if u and u not in out:
                out.append(u)
        return out

    def candidate_urls(self, path: str) -> List[str]:
        if not path.startswith("/"):
            path = "/" + path
        urls: List[str] = []
        for base in self.base_urls:
            urls.append(base + "/api/v1" + path)
            urls.append(base + "/api" + path)
        return urls

    def request(self, method: str, path: str, **kwargs):
        errors: List[str] = []
        attempted: List[str] = []
        timeout = kwargs.pop("timeout", 300)
        for url in self.candidate_urls(path):
            attempted.append(url)
            if self.verbose:
                print(f"[anythingllm] {method} {url}")
            try:
                r = self.session.request(method, url, timeout=timeout, **kwargs)
                if r.status_code in {404, 405}:
                    errors.append(f"{url}: {r.status_code}")
                    continue
                r.raise_for_status()
                self.last_attempts = attempted
                if not r.text:
                    return {}
                try:
                    return r.json()
                except Exception:
                    return {"raw": r.text}
            except Exception as exc:
                errors.append(f"{url}: {exc}")
        self.last_attempts = attempted
        # 网络层 DNS 失败时，附加宿主机/容器的提示，方便排查。
        hint = ""
        joined = "\n".join(errors)
        if "Failed to resolve" in joined or "NameResolutionError" in joined or "Name or service not known" in joined:
            hint = (
                "\n  提示：检测到 DNS 解析失败。\n"
                "  - 宿主机执行：传 --anythingllm-base-url http://localhost:8301，或在 .env 中设 ANYTHINGLLM_BASE_URL=http://localhost:8301\n"
                "  - 容器内执行：使用默认 http://anythingllm:3001 即可，确认 docker compose 已起 anythingllm 服务。"
            )
        raise RuntimeError("; ".join(errors) + hint)

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

    def workspace_details(self, slug: str) -> Dict[str, Any]:
        return self.get(f"/workspace/{slug}")

    def list_users(self) -> List[Dict[str, Any]]:
        data = self.get("/admin/users")
        return data.get("users", []) if isinstance(data, dict) else []

    def ensure_user(self, username: str, password: str, role: str = "default") -> Optional[Dict[str, Any]]:
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


def _workspace_documents(workspace: Any) -> List[Dict[str, Any]]:
    if not isinstance(workspace, dict):
        return []
    w = workspace.get("workspace") or workspace
    if not isinstance(w, dict):
        return []
    docs = w.get("documents") or []
    return docs if isinstance(docs, list) else []


def _remote_doc_refs(workspace: Any) -> set[str]:
    refs: set[str] = set()
    for d in _workspace_documents(workspace):
        if not isinstance(d, dict):
            continue
        for key in ["location", "name", "docpath", "docPath", "id"]:
            val = d.get(key)
            if val:
                refs.add(str(val))
    return refs


def _dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def sync_anythingllm(cfg: Dict[str, Any], sync_users: bool = True, incremental: bool = True) -> Dict[str, Any]:
    """同步工作区、用户和文档。

    - 为每个部门创建 workspace。
    - 尝试创建用户并分配到对应 workspace。
    - 上传 wiki Markdown。
    - 公共文档加入所有部门 workspace，部门文档加入本部门 workspace。
    """
    client = AnythingLLMClient(cfg)
    project_root = Path(cfg["_project_root"])
    print(f"[sync] AnythingLLM 候选地址: {', '.join(client.base_urls)}")
    result = {
        "workspaces": 0,
        "users": 0,
        "uploaded": 0,
        "embedded": 0,
        "skipped_embedded": 0,
        "errors": [],
    }

    with connect(cfg) as conn:
        depts = list_departments(conn)
        docs = list_documents(conn)
        workspace_by_dept: Dict[str, Dict[str, Any]] = {}
        workspace_id_by_dept: Dict[str, int] = {}

        for d in depts:
            try:
                ws = client.ensure_workspace(d["name"], d["slug"])
                workspace_by_dept[d["name"]] = ws
                ws_id = _extract_workspace_id(ws)
                if ws_id:
                    workspace_id_by_dept[d["name"]] = ws_id
                result["workspaces"] += 1
                log_sync(conn, d["slug"], "ensure_workspace", "ok", d["name"])
            except Exception as exc:
                msg = f"workspace {d['name']}: {exc}"
                result["errors"].append(msg)
                log_sync(conn, d["slug"], "ensure_workspace", "error", str(exc))

        if sync_users:
            rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
            users_by_dept: Dict[str, List[int]] = {}
            for u in rows:
                try:
                    user = client.ensure_user(u["username"], u["password"] or "kb123456", u["role"])
                    if user and user.get("id") is not None:
                        user_id = int(user["id"])
                        users_by_dept.setdefault(u["department"], []).append(user_id)
                        conn.execute("UPDATE users SET anythingllm_user_id=? WHERE id=?", (str(user_id), u["id"]))
                        result["users"] += 1
                except Exception as exc:
                    msg = f"user {u['username']}: {exc}"
                    result["errors"].append(msg)
                    log_sync(conn, u["username"], "ensure_user", "error", str(exc))

            for dept_name, user_ids in users_by_dept.items():
                ws_id = workspace_id_by_dept.get(dept_name)
                if not ws_id or not user_ids:
                    continue
                try:
                    client.assign_workspace_users(ws_id, [int(uid) for uid in _dedupe_preserve_order([str(uid) for uid in user_ids])])
                    log_sync(conn, dept_name, "assign_workspace_users", "ok", str(user_ids))
                except Exception as exc:
                    msg = f"assign users {dept_name}: {exc}"
                    result["errors"].append(msg)
                    log_sync(conn, dept_name, "assign_workspace_users", "error", str(exc))

        doc_ref_by_id: Dict[int, str] = {}
        for doc in docs:
            existing_ref = doc["anythingllm_doc_name"]
            if existing_ref and incremental and doc["synced_to_anythingllm"]:
                doc_ref_by_id[int(doc["id"])] = existing_ref
                continue
            try:
                wiki_path = project_root / doc["wiki_path"] if doc["wiki_path"] else None
                if not wiki_path or not wiki_path.exists():
                    continue
                uploaded = client.upload_document(wiki_path, folder_name="kb")
                result["uploaded"] += 1
                ref = _extract_uploaded_ref(uploaded, f"custom-documents/{wiki_path.name}")
                doc_ref_by_id[int(doc["id"])] = ref
                mark_document_uploaded(conn, int(doc["id"]), ref)
                log_sync(conn, doc["title"], "upload_document", "ok", ref)
            except Exception as exc:
                msg = f"upload {doc['title']}: {exc}"
                result["errors"].append(msg)
                log_sync(conn, doc["title"], "upload_document", "error", str(exc))

        slug_by_dept = {d["name"]: d["slug"] for d in depts}
        for dept_name, slug in slug_by_dept.items():
            desired_pairs: List[Tuple[int, str]] = []
            for doc in docs:
                doc_id = int(doc["id"])
                if doc_id not in doc_ref_by_id:
                    continue
                if doc["zone"] == "public" or doc["department"] == dept_name:
                    desired_pairs.append((doc_id, doc_ref_by_id[doc_id]))

            if not desired_pairs:
                continue

            adds = [ref for _, ref in desired_pairs]
            if incremental:
                try:
                    details = client.workspace_details(slug)
                    remote_refs = _remote_doc_refs(details)
                    adds = [ref for ref in adds if ref not in remote_refs]
                except Exception:
                    # 详情接口不可用时，退化为全量 add；AnythingLLM 通常可幂等处理。
                    pass

            adds = _dedupe_preserve_order(adds)
            if not adds:
                result["skipped_embedded"] += len(desired_pairs)
                for doc_id, ref in desired_pairs:
                    mark_workspace_document(conn, slug, doc_id, ref)
                    mark_document_synced(conn, doc_id)
                continue

            try:
                client.update_embeddings(slug, adds)
                result["embedded"] += len(adds)
                for doc_id, ref in desired_pairs:
                    mark_workspace_document(conn, slug, doc_id, ref)
                    mark_document_synced(conn, doc_id)
                log_sync(conn, slug, "update_embeddings", "ok", ",".join(adds))
            except Exception as exc:
                msg = f"embed {dept_name}: {exc}"
                result["errors"].append(msg)
                log_sync(conn, slug, "update_embeddings", "error", str(exc))

        conn.commit()

    return result
