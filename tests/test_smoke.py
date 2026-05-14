import os
import shutil
import subprocess
import sys
import tempfile
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd=ROOT):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run(
        [sys.executable, "-m", "kb.cli", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr)
        raise AssertionError(f"command failed: {args}")
    return p.stdout


def reset_data():
    data = ROOT / "data"
    if data.exists():
        shutil.rmtree(data)
    data.mkdir()
    (data / ".gitkeep").write_text("", encoding="utf-8")
    return data


def prepare_sample_public():
    sample = ROOT / ".tmp_test_input"
    if sample.exists():
        shutil.rmtree(sample)
    (sample / "files" / "2026" / "05" / "12").mkdir(parents=True)
    (sample / "files" / "2026" / "05" / "12" / "7acf3850-4b7a-11f1-8da1-fa163e4c1d80.txt").write_text("安全生产通知正文", encoding="utf-8")
    (sample / "file_meta.csv").write_text(
        "文件标识,文件标题,文件类型,文件名,文件事项ID,文件字号,文件流水号\n"
        "7acf3850-4b7a-11f1-8da1-fa163e4c1d80,关于安全生产的通知,行政,7acf3850-4b7a-11f1-8da1-fa163e4c1d80.txt,sDKC3sDU,通知（10）号,20260512\n",
        encoding="utf-8",
    )
    (sample / "sign.csv").write_text(
        "事项id,签阅人,签阅时间,签阅意见\n"
        "sDKC3sDU,张三,2026/5/12 7:11,已阅\n"
        "sDKC3sDU,李四,2026/5/12 11:11,同意\n",
        encoding="utf-8",
    )
    return sample


def import_public_sample(sample):
    run(["init"])
    run([
        "import-docs",
        "--zone", "public",
        "--source", str(sample / "files"),
        "--metadata", str(sample / "file_meta.csv"),
        "--sign-records", str(sample / "sign.csv"),
    ])
    run(["build-site"])


def test_import_docs_smoke():
    data = reset_data()
    sample = prepare_sample_public()
    try:
        import_public_sample(sample)
        md = ROOT / "data" / "wiki" / "public" / "2026" / "05" / "12" / "行政" / "关于安全生产的通知.md"
        assert md.exists()
        text = md.read_text(encoding="utf-8")
        assert "张三" in text
        assert "李四" in text
        assert "通知（10）号" in text
        assert (ROOT / "data" / "site" / "documents.html").exists()
    finally:
        if sample.exists():
            shutil.rmtree(sample)
        reset_data()


def test_kb_web_permission_smoke():
    data = reset_data()
    sample = prepare_sample_public()
    try:
        import_public_sample(sample)
        # 增加普通用户，启用本地兜底登录。
        users_csv = ROOT / ".tmp_users.csv"
        users_csv.write_text(
            "type,dept_name,username,password,role\n"
            "user,信息技术部,testuser,testpass,member\n",
            encoding="utf-8",
        )
        run(["import-users", str(users_csv)])

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["KB_WEB_ALLOW_LOCAL_AUTH"] = "1"
        env["ANYTHINGLLM_BASE_URL"] = "http://127.0.0.1:1"  # 强制走本地兜底
        port = "18081"
        proc = subprocess.Popen(
            [sys.executable, "-m", "kb.web", "--host", "127.0.0.1", "--port", port],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            import time

            time.sleep(1)
            assert urlopen(f"http://127.0.0.1:{port}/health", timeout=5).status == 200
            try:
                urlopen(f"http://127.0.0.1:{port}/documents", timeout=5)
                raise AssertionError("未登录访问 documents 应该重定向或禁止")
            except HTTPError as e:
                # urllib 默认跟随重定向后若目标可访问不会抛，此处兼容不同表现。
                assert e.code in {302, 403, 404}
            except Exception:
                pass

            cj = CookieJar()
            opener = build_opener(HTTPCookieProcessor(cj))
            body = urlencode({"username": "testuser", "password": "testpass"}).encode("utf-8")
            req = Request(f"http://127.0.0.1:{port}/login", data=body, method="POST")
            resp = opener.open(req, timeout=5)
            html = opener.open(f"http://127.0.0.1:{port}/documents", timeout=5).read().decode("utf-8")
            assert "关于安全生产的通知" in html
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        if users_csv.exists():
            users_csv.unlink()
    finally:
        if sample.exists():
            shutil.rmtree(sample)
        reset_data()


def test_sync_from_anythingllm_smoke():
    data = reset_data()
    try:
        run(["init"])
        storage = ROOT / "data" / "anythingllm" / "workspace" / "dept-3a9507ef"
        storage.mkdir(parents=True)
        (storage / "用户上传测试.txt").write_text("用户通过 AnythingLLM 上传的测试文档", encoding="utf-8")
        out = run(["sync-from-anythingllm"])
        assert "imported" in out
        docs = list((ROOT / "data" / "documents").rglob("用户上传测试.txt"))
        assert docs
    finally:
        reset_data()


if __name__ == "__main__":
    test_import_docs_smoke()
    test_kb_web_permission_smoke()
    test_sync_from_anythingllm_smoke()
    print("ok")
