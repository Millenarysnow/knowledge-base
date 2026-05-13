import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd=ROOT):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run([sys.executable, "-m", "kb.cli", *args], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr)
        raise AssertionError(f"command failed: {args}")
    return p.stdout


def test_import_docs_smoke():
    # 使用项目目录，但先清理 data，确保可重复。
    data = ROOT / "data"
    if data.exists():
        shutil.rmtree(data)
    (data).mkdir()
    (data / ".gitkeep").write_text("", encoding="utf-8")

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

    try:
        run(["init"])
        run([
            "import-docs",
            "--zone", "public",
            "--source", str(sample / "files"),
            "--metadata", str(sample / "file_meta.csv"),
            "--sign-records", str(sample / "sign.csv"),
        ])
        run(["build-site"])
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
        # 保持工作区干净。
        if data.exists():
            shutil.rmtree(data)
        data.mkdir()
        (data / ".gitkeep").write_text("", encoding="utf-8")


if __name__ == "__main__":
    test_import_docs_smoke()
    print("ok")
