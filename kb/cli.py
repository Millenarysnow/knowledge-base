from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

from .config import dept_slug, ensure_dirs, load_config, project_path
from .db import connect, init_db, list_departments, list_documents, upsert_department
from .import_docs import import_docs
from .import_users import import_users
from .site_builder import build_site


def _print_result(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_init(args) -> None:
    cfg = load_config(args.config)
    ensure_dirs(cfg)
    init_db(cfg)
    with connect(cfg) as conn:
        for name in cfg.get("departments", []) or []:
            upsert_department(conn, name, dept_slug(name))
        conn.commit()
    print("✅ 初始化完成")


def cmd_create_dept(args) -> None:
    cfg = load_config(args.config)
    ensure_dirs(cfg)
    init_db(cfg)
    with connect(cfg) as conn:
        upsert_department(conn, args.name, dept_slug(args.name))
        conn.commit()
    print(f"✅ 部门已创建/更新: {args.name}")


def cmd_import_users(args) -> None:
    cfg = load_config(args.config)
    ensure_dirs(cfg)
    init_db(cfg)
    res = import_users(cfg, args.file)
    print(f"✅ 用户导入完成: 部门 {res['departments']} 条, 用户 {res['users']} 条")
    print("ℹ️ 如需同步到 AnythingLLM，请配置 ANYTHINGLLM_API_KEY 后执行 sync-anythingllm。")


def cmd_import_docs(args) -> None:
    cfg = load_config(args.config)
    ensure_dirs(cfg)
    init_db(cfg)
    res = import_docs(
        cfg,
        zone=args.zone,
        dept=args.dept,
        source=args.source,
        metadata=args.metadata,
        sign_records_path=args.sign_records,
    )
    print(f"✅ 文档导入完成: 成功 {res['imported']} 个, 失败 {len(res['failed'])} 个")
    for f, e in res["failed"][:20]:
        print(f"  ❌ {f}: {e}")


def cmd_build_site(args) -> None:
    cfg = load_config(args.config)
    ensure_dirs(cfg)
    init_db(cfg)
    if args.enrich_links:
        from .link_enricher import enrich_wiki_links

        enrich_res = enrich_wiki_links(cfg)
        print("链接补充结果：")
        _print_result(enrich_res)
    res = build_site(cfg)
    print(f"✅ 站点生成完成: {res['site']}，文档 {res['documents']} 个")


def cmd_sync_anythingllm(args) -> None:
    cfg = load_config(args.config)
    ensure_dirs(cfg)
    init_db(cfg)
    from .anythingllm import sync_anythingllm

    res = sync_anythingllm(cfg, sync_users=not args.skip_users, incremental=not args.full)
    _print_result(res)
    if res.get("errors"):
        print("⚠️ 同步出现错误。请打开 AnythingLLM 实例的 /api/docs 核对 API 版本。")


def cmd_sync_from_anythingllm(args) -> None:
    cfg = load_config(args.config)
    ensure_dirs(cfg)
    init_db(cfg)
    from .sync_from_anythingllm import sync_from_anythingllm

    res = sync_from_anythingllm(cfg, storage=args.storage, default_dept=args.default_dept, force=args.force)
    _print_result(res)


def cmd_update(args) -> None:
    cfg = load_config(args.config)
    ensure_dirs(cfg)
    init_db(cfg)
    if args.sync_from_anythingllm:
        from .sync_from_anythingllm import sync_from_anythingllm

        sync_res = sync_from_anythingllm(cfg, storage=args.storage, default_dept=args.default_dept, force=args.force_sync_from_anythingllm)
        print("AnythingLLM 反向同步结果：")
        _print_result(sync_res)
    if args.enrich_links:
        from .link_enricher import enrich_wiki_links

        enrich_res = enrich_wiki_links(cfg)
        print("链接补充结果：")
        _print_result(enrich_res)
    res = build_site(cfg)
    print(f"✅ update 完成：已重建站点，文档 {res['documents']} 个")
    print("ℹ️ 如需同步到 AnythingLLM，请执行 sync-anythingllm。")


def cmd_status(args) -> None:
    cfg = load_config(args.config)
    ensure_dirs(cfg)
    init_db(cfg)
    with connect(cfg) as conn:
        depts = list_departments(conn)
        docs = list_documents(conn)
        print("智能知识库状态")
        print(f"  部门数: {len(depts)}")
        for d in depts:
            print(f"    - {d['name']} ({d['slug']})")
        print(f"  文档数: {len(docs)}")


def _check(name: str, ok: bool, detail: str = "") -> Tuple[str, bool, str]:
    return (name, ok, detail)


def cmd_doctor(args) -> None:
    cfg = load_config(args.config)
    checks = []
    root = Path(cfg["_project_root"])

    checks.append(_check("项目根目录", root.exists(), str(root)))
    checks.append(_check("配置文件", Path(cfg["_config_path"]).exists(), str(cfg["_config_path"])))
    checks.append(_check(".env 文件", (root / ".env").exists(), str(root / ".env")))
    checks.append(_check("docker-compose.yml", (root / "docker-compose.yml").exists(), str(root / "docker-compose.yml")))
    checks.append(_check("ANYTHINGLLM_API_KEY", bool(os.environ.get("ANYTHINGLLM_API_KEY")), "已设置" if os.environ.get("ANYTHINGLLM_API_KEY") else "未设置"))

    try:
        ensure_dirs(cfg)
        init_db(cfg)
        with connect(cfg) as conn:
            depts = list_departments(conn)
            docs = list_documents(conn)
        checks.append(_check("SQLite 数据库", True, str(project_path(cfg, "db"))))
        checks.append(_check("默认部门", len(depts) > 0, f"{len(depts)} 个部门"))
        checks.append(_check("文档数量", True, f"{len(docs)} 个文档"))
    except Exception as exc:
        checks.append(_check("SQLite 数据库", False, str(exc)))

    # 网络检查不作为硬失败，只给提示。
    try:
        import requests

        ollama_url = os.environ.get("OLLAMA_BASE_URL", cfg.get("models", {}).get("ollama_base_url", "http://localhost:11434")).rstrip("/")
        r = requests.get(ollama_url + "/api/tags", timeout=3)
        checks.append(_check("Ollama API", r.status_code == 200, ollama_url))
    except Exception as exc:
        checks.append(_check("Ollama API", False, str(exc)))

    try:
        import requests

        base = os.environ.get("ANYTHINGLLM_BASE_URL", cfg.get("anythingllm", {}).get("base_url", "http://localhost:3001")).rstrip("/")
        r = requests.get(base + "/api/docs", timeout=5)
        # 有些版本 docs 可能需要前端路由，不要求 200。
        checks.append(_check("AnythingLLM /api/docs", r.status_code < 500, f"{base}/api/docs -> {r.status_code}"))
    except Exception as exc:
        checks.append(_check("AnythingLLM /api/docs", False, str(exc)))

    print("智能知识库诊断结果")
    failed = 0
    for name, ok, detail in checks:
        mark = "✅" if ok else "❌"
        if not ok:
            failed += 1
        print(f"  {mark} {name}: {detail}")

    if failed:
        print("\n存在失败项。若是 Ollama/AnythingLLM API 失败，请确认 docker compose up -d 后服务已经启动。")
    else:
        print("\n基础检查通过。")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kbctl", description="智能知识库管理工具")
    p.add_argument("--config", default=None, help="配置文件路径，默认 config/config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="初始化目录、数据库、默认部门")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("create-dept", help="创建/更新部门")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_create_dept)

    sp = sub.add_parser("import-users", help="导入部门和用户 CSV/Excel")
    sp.add_argument("file")
    sp.set_defaults(func=cmd_import_users)

    sp = sub.add_parser("import-docs", help="导入文档，可同时导入元数据和签阅记录")
    sp.add_argument("--zone", choices=["public", "dept"], required=True)
    sp.add_argument("--dept", help="部门名，zone=dept 时必填")
    sp.add_argument("--source", required=True, help="源文件目录")
    sp.add_argument("--metadata", help="文件元数据 CSV/Excel")
    sp.add_argument("--sign-records", help="签阅记录 CSV/Excel")
    sp.set_defaults(func=cmd_import_docs)

    sp = sub.add_parser("build-site", help="生成结构化浏览站点")
    sp.add_argument("--enrich-links", action="store_true", help="向 wiki Markdown 追加 kb-web 文档详情/下载链接")
    sp.set_defaults(func=cmd_build_site)

    sp = sub.add_parser("sync-anythingllm", help="同步工作区、用户和文档到 AnythingLLM")
    sp.add_argument("--skip-users", action="store_true", help="只同步 workspace 和文档，不创建/分配用户")
    sp.add_argument("--full", action="store_true", help="强制全量上传和嵌入，不使用本地同步状态")
    sp.set_defaults(func=cmd_sync_anythingllm)

    sp = sub.add_parser("sync-from-anythingllm", help="从 AnythingLLM 本地存储目录扫描用户上传文件并导入")
    sp.add_argument("--storage", help="AnythingLLM storage 目录，默认 data/anythingllm")
    sp.add_argument("--default-dept", help="无法从路径识别部门时使用的默认部门")
    sp.add_argument("--force", action="store_true", help="忽略反向同步状态，强制重新导入扫描到的文件")
    sp.set_defaults(func=cmd_sync_from_anythingllm)

    sp = sub.add_parser("update", help="增量更新：可选反向同步 AnythingLLM 后重建站点")
    sp.add_argument("--sync-from-anythingllm", action="store_true", help="先扫描 AnythingLLM 本地存储目录导入用户上传文件")
    sp.add_argument("--storage", help="AnythingLLM storage 目录，默认 data/anythingllm")
    sp.add_argument("--default-dept", help="反向同步时无法识别部门的默认部门")
    sp.add_argument("--force-sync-from-anythingllm", action="store_true", help="反向同步时忽略状态，强制重新导入")
    sp.add_argument("--enrich-links", action="store_true", help="向 wiki Markdown 追加 kb-web 文档详情/下载链接")
    sp.set_defaults(func=cmd_update)

    sp = sub.add_parser("doctor", help="诊断配置、数据库和外部服务连通性")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("status", help="查看状态")
    sp.set_defaults(func=cmd_status)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except Exception as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
