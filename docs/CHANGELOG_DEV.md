# 本轮开发改动清单（未提交）

> 时间：2026-05-15
> 背景：根据 `docs/question.md` 反馈的实测问题，做不依赖实机即可完成的修复与增强。
> 后续晚上同学在 Linux Docker 环境再做端到端验证。

## 1. 仓库整理

删除以下不再使用的文件/目录：

- `docker-compose.legacy.yml`
- `llmwiki/` 目录（含 `config.yaml`，旧 llmwiki 误解残留）
- `nginx/` 目录（当前架构 kb-web 直接对外，不需要 nginx）
- `scripts/` 下旧脚本：`ai-classify.py / auto-sort.sh / compile-wiki.sh / create-dept.sh / doc-parser.py / import-dept.sh / import-users.sh / import-view-records.py / manage-workspaces.sh / pull-models.sh / upload-server.py`

保留：`scripts/kbctl.sh`、`scripts/update-kb.sh`。

## 2. 端口与对外 URL

- `docker-compose.yml`：kb-web 由 `80:8000` 改为 `${KB_WEB_PORT:-8081}:8000`，避免 80 被占用。
- `.env` / `.env.example`：新增 `KB_WEB_PORT=8081` 和 `KB_WEB_PUBLIC_URL=http://localhost:8081`。
- README、HANDOFF_STEPS、OPERATIONS、NEXT_STEPS 中所有 `http://localhost` 全部改为 `http://localhost:8081`。

## 3. `.env` 加载链路修复

`kb/config.py` 的 `_load_env_file`：

- 之前：环境变量已存在（即使是空字符串）就跳过 `.env` 值。
- 现在：环境变量为 `None` 或空字符串时，仍用 `.env` 中的真实值覆盖。
- 影响：解决了"docker-compose 用 `${VAR:-}` 注入空字符串后，.env 中的 API_KEY 不生效"的问题。
- 顺带：忽略 BOM、`os.environ.get` 取值后 `.strip()` 防止尾随空格。

`kb/cli.py` 的 `main()`：入口最早就 `load_dotenv()`，避免某些子命令路径漏掉。

## 4. AnythingLLM CLI 与 fallback

- `kb/cli.py` 新增全局参数 `--anythingllm-base-url`，可在命令行直接覆盖（宿主机/容器切换常用）。
- `kb/anythingllm.py`：
  - `request()` 失败时打印每次尝试的 URL；遇到 DNS 解析失败时附加宿主机/容器的提示。
  - `sync_anythingllm` 启动时打印将要尝试的 base_urls。
  - 缺 API_KEY 错误信息明确告诉用户：宿主机 `export` 或 `.env`+重启容器。
  - `KB_VERBOSE=1` 启用每次请求的详细日志。

## 5. 增量导入

`kb/db.py`：

- `documents` 表新增 `import_fingerprint` 字段（含 ALTER TABLE 迁移，重复执行幂等）。
- `init_db` 容忍 "duplicate column" 错误。
- 新增 `find_document_by_identifier(zone, department, file_identifier)`。

`kb/import_docs.py`：

- 新增 `_make_fingerprint(checksum, meta, sign_records)`。
- 导入前先算 fingerprint，命中已有记录则跳过整个解析+落盘流程，输出 `skipped` 计数。
- 新增 `force=False` 参数：`True` 时忽略 fingerprint 强制重新处理。

`kb/cli.py`：`import-docs` 新增 `--force` 标志。

## 6. 链接补充

`kb/link_enricher.py`：

- 之前写相对路径 `/docs/{id}`。
- 现在优先用 `KB_WEB_PUBLIC_URL` 环境变量或 `config.yaml` 的 `site.public_url`，写完整 URL，让 AnythingLLM 引用可点击跳转。
- 配置缺失时退化为相对路径，行为兼容。

`config/config.yaml`：`site` 下新增 `public_url: http://localhost:8081`。

## 7. OCR 兜底骨架

新增 `kb/ocr.py`：

- 优先 PaddleOCR，fallback pytesseract。
- 任何 OCR 引擎都没装时返回空字符串，不阻塞导入。
- `requirements.txt` 不强制声明 OCR 依赖（重量级），文档说明可选安装。

`kb/parser.py` 的 `parse_pdf`：抽不到正文时自动调 `pdf_ocr`，失败仍返回空字符串。

## 8. doctor 增强

`kb/cli.py` 的 `cmd_doctor` 新增检查项：

- `kb-web 公开 URL` 是否设置
- OCR 引擎是否可用
- Ollama 已拉取模型清单（验证 `OLLAMA_MODEL` 和 `EMBEDDING_MODEL`）
- AnythingLLM API Key 有效性（调 `/api/v1/system` 等轻量接口验证）

## 9. 新文档

- `docs/CONFIG.md`：解释 `.env` 与 `config/config.yaml` 的分工、优先级、常见踩坑。
- `docs/CHANGELOG_DEV.md`：本文档。

## 10. 测试结果

`python tests/test_smoke.py`：3 条用例全部通过。

## 11. 待实机验证（同学晚上做）

1. `docker compose up -d` 启动后访问 `http://localhost:8081` 是否正常。
2. `docker exec -it kb-worker python -m kb.cli doctor` 输出每一项是否符合预期。
3. `docker exec -it kb-worker python -m kb.cli sync-anythingllm` 同步是否成功。如失败，把诊断输出（包含尝试的 URL 列表）回传。
4. AnythingLLM 后台核对 `kb/anythingllm.py` 中调用的 5 个 API 路径（workspace/new、admin/users/new、workspace-users、document/upload、update-embeddings）是否一致。
5. 提问"关于安全生产的通知谁签阅了？" 验证签阅记录是否进入了 RAG。
6. 重复跑 `import-docs` 应输出 `未变化跳过 N 个`。
