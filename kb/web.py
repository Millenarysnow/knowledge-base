from __future__ import annotations

import argparse
import html
import os
import posixpath
import secrets
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from .auth import AnythingLLMAuth, AnythingLLMAuthError
from .config import load_config, project_path
from .db import connect, get_document, list_documents

try:
    import markdown
except Exception:  # pragma: no cover
    markdown = None


SESSIONS: Dict[str, Dict[str, Any]] = {}
SESSION_LOCK = threading.Lock()
SESSION_TTL_SECONDS = 12 * 3600

CSS = """
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif;background:#f6f7fb;color:#1f2937}
header{background:#0f172a;color:#fff;padding:16px 28px;display:flex;align-items:center;justify-content:space-between}
header a{color:#bfdbfe;text-decoration:none;margin-left:16px}main{max-width:1180px;margin:0 auto;padding:24px}
.card{background:white;border:1px solid #e5e7eb;border-radius:10px;padding:18px;margin:14px 0;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.table{width:100%;border-collapse:collapse}.table th,.table td{border-bottom:1px solid #e5e7eb;text-align:left;padding:9px}.table th{background:#f8fafc}.muted{color:#6b7280}
.tag{display:inline-block;background:#e0f2fe;color:#0369a1;padding:2px 8px;border-radius:999px;font-size:12px;margin-right:6px}.danger{color:#b91c1c}.ok{color:#15803d}
input{padding:9px;border:1px solid #d1d5db;border-radius:6px;width:280px}button{padding:9px 14px;border:0;border-radius:6px;background:#2563eb;color:#fff;cursor:pointer}a{color:#2563eb}.doc-body{line-height:1.75}.doc-body table{border-collapse:collapse;width:100%;margin:12px 0}.doc-body th,.doc-body td{border:1px solid #e5e7eb;padding:6px 8px}.doc-body th{background:#f8fafc}
"""


def cleanup_sessions() -> None:
    now = time.time()
    with SESSION_LOCK:
        expired = [sid for sid, s in SESSIONS.items() if now - s.get("created_at", 0) > SESSION_TTL_SECONDS]
        for sid in expired:
            SESSIONS.pop(sid, None)


def markdown_to_html(text: str) -> str:
    if markdown is None:
        return "<pre>" + html.escape(text) + "</pre>"
    return markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])


def page(title: str, body: str, user: Optional[Dict[str, Any]] = None) -> bytes:
    user_part = ""
    if user:
        user_part = (
            f"<span>当前用户：{html.escape(user['username'])} "
            f"（{html.escape(user.get('role') or '')} / {html.escape(user.get('department') or '')}）</span>"
            "<a href='/logout'>退出</a>"
        )
    else:
        user_part = "<a href='/login'>登录</a>"
    text = f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{CSS}</style></head>
<body><header><div><strong>智能知识库</strong><a href='/'>首页</a><a href='/documents'>文档</a><a href='/graph'>知识图谱</a></div><nav>{user_part}</nav></header><main>{body}</main></body></html>"""
    return text.encode("utf-8")


class KBWebHandler(BaseHTTPRequestHandler):
    cfg: Dict[str, Any] = {}

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[kb-web] {self.address_string()} - {fmt % args}")

    def send_html(self, body: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def current_session(self) -> Optional[Dict[str, Any]]:
        cleanup_sessions()
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("kb_session")
        if not morsel:
            return None
        with SESSION_LOCK:
            return SESSIONS.get(morsel.value)

    def require_user(self) -> Optional[Dict[str, Any]]:
        s = self.current_session()
        if not s:
            self.redirect("/login")
            return None
        return s

    def local_user(self, username: str) -> Optional[Dict[str, Any]]:
        with connect(self.cfg) as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            return dict(row) if row else None

    def can_access_doc(self, user: Dict[str, Any], doc: Any) -> bool:
        role = (user.get("role") or "").lower()
        if role == "admin":
            return True
        if doc["zone"] == "public":
            return True
        return (doc["department"] or "") == (user.get("department") or "")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK\n")
            return
        if path == "/login":
            self.handle_login_get()
            return
        if path == "/logout":
            self.handle_logout()
            return

        user = self.require_user()
        if not user:
            return

        if path == "/" or path == "/index.html":
            self.handle_index(user)
        elif path == "/documents":
            self.handle_documents(user)
        elif path.startswith("/docs/"):
            self.handle_doc_detail(user, path)
        elif path.startswith("/files/"):
            self.handle_file(user, path)
        elif path == "/graph":
            self.handle_graph(user)
        else:
            self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/login":
            self.handle_login_post()
        else:
            self.send_error(404, "Not Found")

    def handle_login_get(self, error: str = "") -> None:
        body = """
<div class='card'><h1>登录智能知识库</h1>
<p class='muted'>使用 AnythingLLM 账号密码登录。登录后按本地用户表控制文档浏览权限。</p>
<form method='post' action='/login'>
<p><label>用户名<br><input name='username' autocomplete='username'></label></p>
<p><label>密码<br><input name='password' type='password' autocomplete='current-password'></label></p>
<p><button type='submit'>登录</button></p>
</form>
"""
        if error:
            body += f"<p class='danger'>{html.escape(error)}</p>"
        body += "</div>"
        self.send_html(page("登录", body))

    def handle_login_post(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        form = urllib.parse.parse_qs(raw)
        username = (form.get("username") or [""])[0].strip()
        password = (form.get("password") or [""])[0]
        if not username or not password:
            self.handle_login_get("请输入用户名和密码")
            return

        local = self.local_user(username)
        if not local:
            self.handle_login_get("该用户未导入本地用户表，请先执行 import-users")
            return

        allow_local_fallback = os.environ.get("KB_WEB_ALLOW_LOCAL_AUTH", "").lower() in {"1", "true", "yes"}
        auth_ok = False
        token = ""
        auth_error = ""
        try:
            base_url = os.environ.get("ANYTHINGLLM_BASE_URL", self.cfg.get("anythingllm", {}).get("base_url", "http://localhost:3001"))
            data = AnythingLLMAuth(base_url).request_token(username, password)
            auth_ok = True
            token = data.get("token") or ""
        except Exception as exc:
            auth_error = str(exc)
            if allow_local_fallback and (local.get("password") or "") == password:
                auth_ok = True

        if not auth_ok:
            self.handle_login_get(f"AnythingLLM 登录失败：{auth_error}")
            return

        sid = secrets.token_urlsafe(32)
        with SESSION_LOCK:
            SESSIONS[sid] = {
                "username": username,
                "department": local.get("department"),
                "role": local.get("role"),
                "anythingllm_token": token,
                "created_at": time.time(),
            }
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie", f"kb_session={sid}; Path=/; HttpOnly; SameSite=Lax")
        self.end_headers()

    def handle_logout(self) -> None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("kb_session")
        if morsel:
            with SESSION_LOCK:
                SESSIONS.pop(morsel.value, None)
        self.send_response(302)
        self.send_header("Location", "/login")
        self.send_header("Set-Cookie", "kb_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
        self.end_headers()

    def accessible_docs(self, user: Dict[str, Any]):
        with connect(self.cfg) as conn:
            docs = list_documents(conn)
        return [d for d in docs if self.can_access_doc(user, d)]

    def handle_index(self, user: Dict[str, Any]) -> None:
        docs = self.accessible_docs(user)
        body = f"""
<div class='card'><h1>智能知识库</h1>
<p>你当前可访问 <strong>{len(docs)}</strong> 篇文档。</p>
<p class='muted'>权限规则：管理员可访问全部；普通用户只能访问公共区 + 本部门。</p>
</div>
<div class='card'><h2>快捷入口</h2><p><a href='/documents'>查看文档列表</a> · <a href='/graph'>查看知识图谱</a></p></div>
"""
        self.send_html(page("智能知识库", body, user))

    def handle_documents(self, user: Dict[str, Any]) -> None:
        docs = self.accessible_docs(user)
        rows = []
        for d in docs:
            zone = "公共区" if d["zone"] == "public" else f"部门：{d['department']}"
            rows.append(
                f"<tr><td><a href='/docs/{d['id']}'>{html.escape(d['title'])}</a></td>"
                f"<td>{html.escape(d['category'] or '')}</td><td>{html.escape(zone)}</td>"
                f"<td>{html.escape(d['doc_number'] or '')}</td><td>{html.escape(d['item_id'] or '')}</td></tr>"
            )
        body = "<div class='card'><h1>文档列表</h1><table class='table'><thead><tr><th>标题</th><th>分类</th><th>区域</th><th>字号</th><th>事项ID</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        self.send_html(page("文档列表", body, user))

    def handle_doc_detail(self, user: Dict[str, Any], path: str) -> None:
        raw_id = path.rstrip("/").split("/")[-1]
        if raw_id.endswith(".html"):
            raw_id = raw_id[:-5]
        if not raw_id.isdigit():
            self.send_error(404, "Invalid document id")
            return
        with connect(self.cfg) as conn:
            doc = get_document(conn, int(raw_id))
        if not doc:
            self.send_error(404, "Document not found")
            return
        if not self.can_access_doc(user, doc):
            self.send_error(403, "Forbidden")
            return
        wiki_path = Path(self.cfg["_project_root"]) / doc["wiki_path"] if doc["wiki_path"] else None
        if wiki_path and wiki_path.exists():
            md = wiki_path.read_text(encoding="utf-8")
        else:
            md = f"# {doc['title']}\n\n（未生成结构化内容）"
        body = f"<div class='card'><p><a href='/documents'>← 返回文档列表</a></p><div class='doc-body'>{markdown_to_html(md)}</div><p><a href='/files/{doc['id']}'>下载原文件</a></p></div>"
        self.send_html(page(doc["title"], body, user))

    def resolve_file_doc(self, path: str):
        rel = urllib.parse.unquote(path[len("/files/"):]).strip("/")
        with connect(self.cfg) as conn:
            if rel.isdigit():
                return get_document(conn, int(rel))
            # 兼容旧静态页面中的 /files/public/... 路径。
            target_suffix = rel.replace("/", os.sep)
            docs = list_documents(conn)
            for d in docs:
                stored = d["stored_path"] or ""
                if stored.replace("\\", "/").endswith(rel):
                    return d
                if stored.endswith(target_suffix):
                    return d
        return None

    def handle_file(self, user: Dict[str, Any], path: str) -> None:
        doc = self.resolve_file_doc(path)
        if not doc:
            self.send_error(404, "File not found")
            return
        if not self.can_access_doc(user, doc):
            self.send_error(403, "Forbidden")
            return
        file_path = Path(self.cfg["_project_root"]) / doc["stored_path"]
        if not file_path.exists():
            self.send_error(404, "File missing on disk")
            return
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(file_path.name)}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_graph(self, user: Dict[str, Any]) -> None:
        docs = self.accessible_docs(user)
        nodes = []
        edges = []
        item_nodes = set()
        for d in docs:
            nodes.append({"id": f"doc-{d['id']}", "label": d["title"]})
            if d["item_id"]:
                item_id = d["item_id"]
                if item_id not in item_nodes:
                    item_nodes.add(item_id)
                    nodes.append({"id": f"item-{item_id}", "label": f"事项 {item_id}"})
                edges.append({"from": f"item-{item_id}", "to": f"doc-{d['id']}"})
        import json

        body = f"<div class='card'><h1>知识图谱</h1><p class='muted'>当前 MVP 图谱：事项ID ↔ 可访问文档。</p><pre>{html.escape(json.dumps({'nodes': nodes, 'edges': edges}, ensure_ascii=False, indent=2))}</pre></div>"
        self.send_html(page("知识图谱", body, user))


def run(host: str, port: int, config_path: str | None = None) -> None:
    cfg = load_config(config_path)
    KBWebHandler.cfg = cfg
    server = ThreadingHTTPServer((host, port), KBWebHandler)
    print(f"kb-web listening on http://{host}:{port}")
    server.serve_forever()


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="智能知识库权限浏览服务")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)
    run(args.host, args.port, args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
