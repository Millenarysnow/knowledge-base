#!/usr/bin/env python3
"""
智能知识库 - 部门文件上传服务
为部门用户提供 Web 上传界面

用法:
    python3 upload-server.py [port]

端点:
    GET  /upload             上传页面
    POST /api/upload          上传文件 (multipart: file, dept, category?)
    GET  /api/files?dept=XX   查看本部门文件列表
    GET  /api/download?dept=XX&file=YY  下载文件
"""
import os
import sys
import json
import re
import shutil
import pathlib
import hashlib
import mimetypes
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DOCUMENTS_ROOT = pathlib.Path("/app/documents")

HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>智能知识库 - 部门文档上传</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
.container{max-width:960px;margin:0 auto;padding:2rem}
header{margin-bottom:2rem;border-bottom:1px solid #334155;padding-bottom:1rem}
h1{font-size:1.5rem;color:#f8fafc}
.subtitle{color:#94a3b8;font-size:0.875rem;margin-top:0.25rem}
.actions{display:flex;gap:0.75rem;margin-bottom:1.5rem;flex-wrap:wrap}
.btn{padding:0.5rem 1.25rem;border:none;border-radius:0.375rem;cursor:pointer;font-size:0.875rem;font-weight:500;transition:opacity .2s}
.btn:hover{opacity:0.85}
.btn-primary{background:#3b82f6;color:white}
.btn-success{background:#22c55e;color:white}
.btn-secondary{background:#475569;color:white}
.btn-danger{background:#ef4444;color:white}
.card{background:#1e293b;border-radius:0.5rem;padding:1.5rem;margin-bottom:1rem}
.form-group{margin-bottom:1rem}
label{display:block;margin-bottom:0.25rem;color:#94a3b8;font-size:0.875rem}
select,input[type=text]{padding:0.5rem;border-radius:0.375rem;border:1px solid #475569;background:#0f172a;color:#e2e8f0;font-size:0.875rem;width:100%;max-width:300px}
.upload-zone{border:2px dashed #475569;border-radius:0.5rem;padding:3rem 2rem;text-align:center;cursor:pointer;transition:border-color .2s,background .2s;margin-bottom:1rem}
.upload-zone:hover,.upload-zone.dragover{border-color:#3b82f6;background:rgba(59,130,246,0.1)}
.upload-zone p{color:#94a3b8;margin-top:0.5rem}
.file-input{display:none}
.file-list{display:flex;flex-wrap:wrap;gap:0.5rem;margin-bottom:1rem}
.file-tag{background:#334155;padding:0.25rem 0.75rem;border-radius:9999px;font-size:0.8rem;display:flex;align-items:center;gap:0.5rem}
.file-tag button{background:none;border:none;color:#f87171;cursor:pointer;font-size:1rem}
table{width:100%;border-collapse:collapse}
th,td{padding:0.75rem 1rem;text-align:left;border-bottom:1px solid #334155}
th{color:#94a3b8;font-weight:500;font-size:0.8rem;text-transform:uppercase}
.status{display:inline-block;padding:0.125rem 0.5rem;border-radius:9999px;font-size:0.75rem}
.status-ok{background:rgba(34,197,94,0.15);color:#4ade80}
.status-err{background:rgba(239,68,68,0.15);color:#f87171}
.log-panel{background:#0f172a;border-radius:0.375rem;padding:1rem;max-height:200px;overflow-y:auto;font-family:monospace;font-size:0.8rem;color:#94a3b8;white-space:pre-wrap;display:none}
</style>
</head>
<body>
<div class="container">
<header>
<h1>智能知识库 — 部门文档上传</h1>
<p class="subtitle">上传文档到本部门知识库，支持 PDF / DOCX / DOC / WPS / MD / TXT</p>
</header>

<div class="card">
<div class="form-group">
<label>选择部门</label>
<select id="deptSelect">
<option value="">加载中...</option>
</select>
</div>
<div class="form-group">
<label>指定分类（可选，留空则自动识别）</label>
<select id="categorySelect">
<option value="">自动识别</option>
<option value="行政">行政制度</option>
<option value="技术">技术文档</option>
<option value="会议">会议纪要</option>
<option value="报告">工作报告</option>
</select>
</div>

<div class="upload-zone" id="dropZone">
<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
<p>点击或拖拽文件到此处上传</p>
<p style="font-size:0.8rem">文件将按日期组织：YYYY/MM/DD/分类/文件名</p>
</div>
<input type="file" id="fileInput" class="file-input" multiple accept=".pdf,.docx,.doc,.wps,.md,.txt">

<div class="file-list" id="selectedFiles"></div>

<button class="btn btn-success" onclick="uploadFiles()">上传文件</button>
</div>

<div class="card">
<h3 style="margin-bottom:1rem">本部门已上传文件</h3>
<table>
<thead><tr><th>文件名</th><th>分类</th><th>上传日期</th><th>大小</th><th>下载</th></tr></thead>
<tbody id="fileTable"><tr><td colspan="5" style="color:#64748b">选择部门后加载文件列表</td></tr></tbody>
</table>
</div>

<div class="log-panel" id="logPanel"></div>
</div>

<script>
const DROP=document.getElementById('dropZone');
const LOG=document.getElementById('logPanel');
let selectedFiles=new DataTransfer();

function log(msg){LOG.style.display='block';LOG.textContent+=msg+'\\n';}

['dragover','dragenter'].forEach(e=>DROP.addEventListener(e,ev=>{ev.preventDefault();DROP.classList.add('dragover');}));
['dragleave','dragend','drop'].forEach(e=>DROP.addEventListener(e,ev=>{ev.preventDefault();DROP.classList.remove('dragover');}));
DROP.addEventListener('drop',e=>{
for(const f of e.dataTransfer.files){selectedFiles.items.add(f);}
renderSelected();
});

document.getElementById('fileInput').addEventListener('change',e=>{
for(const f of e.target.files){selectedFiles.items.add(f);}
renderSelected();
});

function renderSelected(){
const div=document.getElementById('selectedFiles');
const files=Array.from(selectedFiles.files);
div.innerHTML=files.map((f,i)=>`<span class="file-tag">${f.name} <button onclick="removeFile(${i})">×</button></span>`).join('');
}

function removeFile(i){
const dt=new DataTransfer();
Array.from(selectedFiles.files).forEach((f,idx)=>{if(idx!==i)dt.items.add(f);});
selectedFiles=dt;renderSelected();
}

async function uploadFiles(){
const dept=document.getElementById('deptSelect').value;
const category=document.getElementById('categorySelect').value;
if(!dept){alert('请选择部门');return;}
if(!selectedFiles.files.length){alert('请选择文件');return;}

const form=new FormData();
Array.from(selectedFiles.files).forEach(f=>form.append('files',f));
form.append('dept',dept);
form.append('category',category);

log('上传中...');
const r=await fetch('/api/upload',{method:'POST',body:form});
const d=await r.json();
log(JSON.stringify(d,null,2));
selectedFiles=new DataTransfer();renderSelected();loadFiles();
}

async function loadFiles(){
const dept=document.getElementById('deptSelect').value;
if(!dept)return;
try{
const r=await fetch('/api/files?dept='+encodeURIComponent(dept));
const d=await r.json();
const tbody=document.getElementById('fileTable');
if(!d.files||!d.files.length){tbody.innerHTML='<tr><td colspan="5" style="color:#64748b">暂无文件</td></tr>';return;}
tbody.innerHTML=d.files.map(f=>`<tr>
<td>${f.name}</td><td>${f.category||'-'}</td><td>${f.date||'-'}</td><td>${f.size||'-'}</td>
<td><a href="/api/download?dept=${encodeURIComponent(dept)}&file=${encodeURIComponent(f.path||'')}" style="color:#3b82f6;text-decoration:none">下载</a></td>
</tr>`).join('');
}catch(e){}
}

// 加载部门列表
(async function(){
try{
const r=await fetch('/api/depts');
const d=await r.json();
const sel=document.getElementById('deptSelect');
sel.innerHTML=d.depts.map(d=>`<option value="${d}">${d}</option>`).join('');
loadFiles();
}catch(e){sel.innerHTML='<option>加载失败</option>';}
})();

document.getElementById('deptSelect').addEventListener('change',loadFiles);
</script>
</body>
</html>"""


class UploadHandler(BaseHTTPRequestHandler):
    """处理文件上传的 HTTP 服务器"""

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/upload":
            self._serve_html(HTML_PAGE)
        elif parsed.path == "/api/depts":
            self._json_response({"depts": list_depts()})
        elif parsed.path == "/api/files":
            params = parse_qs(parsed.query)
            dept = params.get("dept", [""])[0]
            self._json_response({"files": list_files(dept)})
        elif parsed.path == "/api/download":
            params = parse_qs(parsed.query)
            dept = params.get("dept", [""])[0]
            file_rel = params.get("file", [""])[0]
            self._serve_download(dept, file_rel)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        if self.path == "/api/upload":
            self._handle_upload()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def _handle_upload(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Expect multipart/form-data")
            return

        # 解析 multipart 数据
        boundary = content_type.split("boundary=")[1].encode()
        body = self.rfile.read(int(self.headers["Content-Length"]))

        files_data = parse_multipart(body, boundary)
        dept = files_data.get("dept", ["unknown"])[0]
        category = files_data.get("category", [""])[0]

        results = []
        today = datetime.now().strftime("%Y/%m/%d")

        for field_name, content in files_data.get("files_raw", []):
            filename, file_bytes = content
            if not filename:
                continue

            # 自动判定分类
            if not category:
                cat = auto_classify(filename)
            else:
                cat = category

            # 构建目标路径: dept-XX/YYYY/MM/DD/分类/文件名
            dest_dir = DOCUMENTS_ROOT / f"dept-{dept}" / today / cat
            dest_dir.mkdir(parents=True, exist_ok=True)

            dest_file = dest_dir / filename
            dest_file.write_bytes(file_bytes)

            file_size = len(file_bytes)
            results.append({
                "filename": filename,
                "category": cat,
                "path": str(dest_file.relative_to(DOCUMENTS_ROOT)),
                "size": f"{file_size / 1024:.1f} KB",
                "status": "ok"
            })

        self._json_response({"success": True, "results": results})

    def _serve_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _serve_download(self, dept, file_rel):
        file_path = DOCUMENTS_ROOT / file_rel
        dept_prefix = f"dept-{dept}/"
        if not file_rel.startswith(dept_prefix):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden: can only download files from your department")
            return
        if not file_path.exists():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"File not found")
            return
        content_type, _ = mimetypes.guess_type(str(file_path))
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Disposition",
                         f'attachment; filename="{file_path.name}"')
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def _json_response(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[upload-server] {args[0]}")


def list_depts():
    """列出所有部门"""
    depts = ["public"]
    if DOCUMENTS_ROOT.exists():
        for d in DOCUMENTS_ROOT.iterdir():
            if d.is_dir() and d.name.startswith("dept-"):
                depts.append(d.name.replace("dept-", "", 1))
    return depts


def list_files(dept):
    """列出指定部门的文件"""
    dept_dir = DOCUMENTS_ROOT / f"dept-{dept}"
    if not dept_dir.exists():
        return []
    files = []
    for f in sorted(dept_dir.rglob("*"), reverse=True):
        if f.is_file() and not f.name.startswith("."):
            rel = f.relative_to(DOCUMENTS_ROOT)
            parts = rel.parts
            # 健壮解析：匹配 dept-XX/YYYY/MM/DD/分类/文件名 或更简单的结构
            date_str = "-"
            cat = "-"
            if len(parts) >= 2 and re.match(r'^\d{4}$', parts[1]):
                date_parts = []
                for i in range(1, min(len(parts), 4)):
                    if re.match(r'^\d{2,4}$', parts[i]):
                        date_parts.append(parts[i])
                    else:
                        break
                date_str = "/".join(date_parts) if date_parts else "-"
                # 日期之后的部分为分类
                date_end = 1 + len(date_parts)
                if len(parts) > date_end:
                    cat = parts[date_end]
            size = f"{f.stat().st_size / 1024:.1f} KB"
            files.append({
                "name": f.name,
                "path": str(rel),
                "category": cat,
                "date": date_str,
                "size": size
            })
    return files[:50]


def auto_classify(filename):
    """根据文件名自动判定分类"""
    name = filename.lower()
    if any(k in name for k in ["会议", "纪要", "讨论", "决议", "复盘", "例会", "评审"]):
        return "会议"
    if any(k in name for k in ["报告", "总结", "汇报", "分析", "调研", "统计", "年度", "季度", "评估"]):
        return "报告"
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext in ("docx", "doc", "wps", "ofd"):
        return "行政"
    return "技术"


def parse_multipart(body, boundary):
    """简易 multipart/form-data 解析"""
    result = {}
    raw_files = []
    parts = body.split(b"--" + boundary)
    for part in parts:
        if b"Content-Disposition" not in part:
            continue
        header_end = part.find(b"\r\n\r\n")
        if header_end < 0:
            continue
        header = part[:header_end].decode("utf-8", errors="replace")
        content = part[header_end + 4:]
        if content.endswith(b"\r\n"):
            content = content[:-2]

        if 'name="dept"' in header:
            result["dept"] = [content.decode("utf-8", errors="replace").strip()]
        elif 'name="category"' in header:
            result["category"] = [content.decode("utf-8", errors="replace").strip()]
        elif 'name="files"' in header or 'filename="' in header:
            fname_start = header.find('filename="') + 10
            fname_end = header.find('"', fname_start)
            fname = header[fname_start:fname_end] if fname_end > fname_start else "unknown"
            raw_files.append((fname, content))

    if raw_files:
        result["files_raw"] = raw_files
    return result


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    print(f"智能知识库 - 部门上传服务")
    print(f"访问地址: http://0.0.0.0:{port}/upload")
    server = HTTPServer(("0.0.0.0", port), UploadHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
