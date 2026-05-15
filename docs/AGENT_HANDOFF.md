# Agent 交接文档（给下一个 AI agent）

> 你即将接手这个仓库的开发。读完本文档你应该能：理解项目要做什么、当前在哪、怎么继续、避开哪些坑。
> 预计阅读时间 10 分钟。读完再看 `docs/CHANGELOG_DEV.md` 了解上一轮（即"我"）做了什么。

---

## 1. 项目本质（30 秒）

本地化部署的**企业团队智能知识库**。甲方原话："里面有 AI 方面比较有用的各个开源项目，包括 RAG、智能体、本地模型部署，文档管理和识别"。

```text
Ollama          本地 LLM + Embedding（默认 qwen2.5:7b / bge-m3，低配可换 1.5b）
AnythingLLM     用户认证 / 部门 workspace / 用户GUI上传 / RAG 问答
kb (Python CLI) 批量导入 / 元数据&签阅记录绑定 / 解析 / 结构化Markdown / AnythingLLM API同步
kb-web          按部门权限的浏览与下载（替代 nginx 直接暴露）
```

需求来源（按权威度排序）：

1. `doc/需求.md` —— 甲方文字版需求
2. `E:\Others\Image` 下的微信截图 —— 甲方与同学的对话原文，关键决策都在里面（"用户上传只能走 AnythingLLM 界面"、"批量导入用脚本不要 UI"、"签阅记录必须进 RAG"等）
3. `docs/REBUILD_PLAN.md` / `docs/DESIGN.md` —— 项目维护者从 1+2 提炼的需求
4. `docs/ARCHITECTURE_THINKING.md` —— **重要**：解释为什么放弃 Pratiyush/llm-wiki 重新设计

不要再回去重读 1+2，除非 3+4 里有矛盾。

---

## 2. 关键业务约定（必读，否则代码改错）

### 2.1 区域 / 部门

```text
zone = public | dept
public 区：所有用户可访问
dept 区：仅本部门用户可访问
```

默认三个部门：`信息技术部 / 办公室 / 研究室`，配置在 `config/config.yaml` 的 `departments`。

每个部门有一个 AnythingLLM workspace，slug = `dept-{md5(name)[:8]}`，例如：

```text
信息技术部 → dept-3a9507ef
办公室    → dept-93cfc1e1
研究室    → dept-bf49d0f4
```

不用中文 slug，避免 API 兼容问题。计算函数：`kb/config.py::dept_slug`。

### 2.2 文档落盘路径

```text
data/documents/{zone_dir}/YYYY/MM/DD/{category}/{filename}
  zone_dir 取值：public 或 dept-{部门名}
data/raw/...   ← 解析后的纯文本
data/wiki/...  ← 结构化 Markdown（含 frontmatter / 文件信息表 / 签阅记录表 / 正文）
data/site/...  ← 静态站点（kb-web 不依赖它，纯调试产物）
data/db/kb.sqlite3
```

日期来源优先级：源目录中 `YYYY/MM/DD` 段 → 否则当天。

### 2.3 分类优先级（重要）

```text
元数据表分类 > 目录分类 > 文件名/内容关键词分类 > AI 分类 > 未分类
```

**绝对不能**把 AI 分类放前面。甲方明确说过元数据是上游来的可信字段，AI 只能兜底。`kb/import_docs.py::import_docs` 严格按这个顺序。

### 2.4 元数据表 / 签阅记录表

```csv
# 文件元数据
文件标识,文件标题,文件类型,文件名,文件事项ID,文件字号,文件流水号

# 签阅记录
事项id,签阅人,签阅时间,签阅意见
```

关联键：`文件元数据.文件事项ID == 签阅记录.事项id`，一个事项 ID 可对应**多个文件**和**多条签阅记录**。

字段别名映射在 `kb/import_docs.py` 顶部：`META_*` / `SIGN_*` 常量。

### 2.5 签阅记录必须进入 RAG

这是甲方的核心需求。实现方式：在结构化 Markdown 里把签阅表格写入正文，AnythingLLM 把 Markdown 入 embedding 后，问"谁签阅了 X"时能命中。

不要走"签阅记录单独存表然后用 SQL 检索"——AnythingLLM 看不到 SQL，Markdown 是唯一上下文。

### 2.6 AnythingLLM workspace 隔离规则

```text
公共区文档 → 同步到所有部门 workspace
部门区文档 → 只同步到本部门 workspace
```

同步逻辑：`kb/anythingllm.py::sync_anythingllm`。

### 2.7 用户上传走 AnythingLLM 界面

甲方明确说部门用户**不通过我们的 import-docs 上传**，他们用 AnythingLLM 的 GUI 上传。我们要做的是：定时跑 `sync-from-anythingllm`，把 AnythingLLM 存储目录里的文件反向扫到本地知识库，让 kb-web 也能浏览/下载。

实现：`kb/sync_from_anythingllm.py`。**当前是兜底扫描实现**，等同学回传真实 AnythingLLM 存储目录结构后才能精确化。

---

## 3. 仓库结构地图

```
knowledge-base/
├── config/config.yaml          业务字典：部门、分类关键词、模型默认地址
├── docker-compose.yml          4 个服务：kb-ollama / kb-anythingllm / kb-worker / kb-web
├── .env / .env.example         敏感凭据 + 部署差异
├── kb/                         所有核心 Python 代码
│   ├── cli.py                  命令行总入口（init/import-*/build-site/sync-*/doctor/status）
│   ├── config.py               YAML + .env 加载，dept_slug 计算
│   ├── db.py                   SQLite schema + upsert/find 函数
│   ├── util.py                 CSV/Excel 读取、文件 hash、安全文件名
│   ├── parser.py               PDF/DOCX/DOC/WPS/OFD/MD/TXT 解析
│   ├── ocr.py                  PaddleOCR / pytesseract 双引擎兜底（PDF 抽不到正文时调用）
│   ├── ollama.py               Ollama chat / 可用性检测
│   ├── import_users.py         用户/部门 CSV 导入
│   ├── import_docs.py          ★ 文档导入主流程，含分类策略 + 增量 fingerprint
│   ├── anythingllm.py          ★ AnythingLLM API 客户端 + sync_anythingllm
│   ├── sync_from_anythingllm.py 反向扫描 AnythingLLM 存储目录
│   ├── auth.py                 AnythingLLM /api/request-token 封装
│   ├── web.py                  kb-web HTTP 服务（http.server，无 framework 依赖）
│   ├── link_enricher.py        往 wiki Markdown 写完整跳转 URL
│   └── site_builder.py         data/site 静态站点生成（调试用）
├── scripts/
│   ├── kbctl.sh                Linux 转发到 python -m kb.cli
│   └── update-kb.sh            cron/定时入口
├── tests/test_smoke.py         3 条冒烟测试，必跑
├── data/                       运行时产物，被 .gitignore（除 .gitkeep）
├── doc/                        甲方原始需求 + 截图
├── docs/                       项目内部文档（本文件就在这里）
└── users.csv                   默认 admin 账号示例
```

带 ★ 的两个文件是接下来最常改的。

---

## 4. 当前位置（最近一轮做了什么）

详见 [`docs/CHANGELOG_DEV.md`](CHANGELOG_DEV.md)。摘要：

- 修了同学 [`docs/question.md`](question.md) 反馈的 4 个痛点（端口冲突、`.env` 加载、宿主机解析失败、配置分工不清）
- 删了 11 个旧脚本 + 旧 compose + nginx 目录 + llmwiki 误解残留
- 加了 `import-docs` 增量 fingerprint（重复跑会输出 `跳过 N 个`）
- 加了 OCR 兜底骨架（依赖按需装）
- 加了 doctor 增强（含 Ollama 模型清单、API Key 有效性、宿主机 fallback）
- 加了 `--anythingllm-base-url` CLI 参数
- 写了 `docs/CONFIG.md` 解释 `.env` vs `config.yaml`
- 冒烟测试 3 条全过

---

## 5. 接下来你最可能要做的事（按优先级）

### P0：等同学晚上回传实机数据后做

同学会回传：

1. `docker exec kb-worker python -m kb.cli doctor` 输出
2. `sync-anythingllm` 输出（含候选地址日志）
3. AnythingLLM `/api/docs` 实际接口路径
4. AnythingLLM 用户上传文件后的 `data/anythingllm` 目录结构
5. 任何一步的报错

**最重要的事：根据 #3 修 `kb/anythingllm.py` 里的 5 个接口路径**：

```python
# 当前 kb/anythingllm.py 用的路径（双 fallback /api/v1 → /api）：
ensure_workspace      → /workspace/new        + GET /workspaces
list_users            → /admin/users
ensure_user           → /admin/users/new
assign_workspace_users→ /admin/workspace-users
upload_document       → /document/upload[/{folder}]
upload_and_embed      → /workspace/{slug}/upload-and-embed
update_embeddings     → /workspace/{slug}/update-embeddings
```

按 `/api/docs` 实际路径调整即可。代码已经把每次尝试的 URL 都打印出来，错误信息里看得到。

### P1：用户上传反向同步精确化

`kb/sync_from_anythingllm.py` 当前是目录扫描兜底。同学回传的 #4 应能告诉你：

- 用户上传的文件实际存在哪里（典型路径如 `data/anythingllm/documents/custom-documents/...` 或某 workspace 子目录）
- 是否能从路径推断出归属 workspace

如果有 AnythingLLM API 列文档，改成 API 精确同步会比目录扫描可靠。

### P2：来源 citation 跳 kb-web

已部分完成：`kb/link_enricher.py` 把完整 URL 写进 Markdown。AnythingLLM 引用展示时可能只显示文件名，需要实测看看。

可能的方案：

- 在 frontmatter 加 `source_url: http://kb-web:8081/docs/{id}`
- 在正文末尾加可点击链接（已实现）
- 如果 AnythingLLM 支持自定义 metadata，上传时携带 doc_id

### P3 及以后：见 `docs/NEXT_STEPS.md`

OCR 引擎默认安装、知识图谱可视化、增量同步缓存、`scripts/update-kb.sh` 定时优化等。

---

## 6. 调试/开发技巧

### 6.1 本地快速验证（不需要 docker）

```bash
python -m kb.cli init
python tests/test_smoke.py
python -m kb.cli doctor
```

冒烟测试覆盖：导入 + Markdown 生成 + kb-web 兜底登录 + sync-from-anythingllm。

### 6.2 让 AnythingLLM 客户端打印每次请求

```bash
KB_VERBOSE=1 python -m kb.cli sync-anythingllm
```

`kb/anythingllm.py::AnythingLLMClient.request` 会打印 `[anythingllm] METHOD URL` 给每次尝试。

### 6.3 宿主机 / 容器执行的差别

```bash
# 容器内（推荐）
docker exec -it kb-worker python -m kb.cli sync-anythingllm

# 宿主机（必须传 --anythingllm-base-url）
python -m kb.cli --anythingllm-base-url http://localhost:8301 sync-anythingllm
# 或在 .env 里设 ANYTHINGLLM_BASE_URL=http://localhost:8301
```

代码里已为常见的 `anythingllm` ↔ `localhost:8301` 双向 fallback，但显式传比较省心。

### 6.4 Windows 终端 emoji 输出

`kb/cli.py::main` 已 `sys.stdout.reconfigure(encoding="utf-8")`。直接 `print` emoji 可能报错的代码，请走 CLI 入口。

### 6.5 修改 `.env` 后

容器是 docker-compose 启动时一次性注入环境变量的。改完 `.env` **必须** `docker compose restart kb-worker kb-web`。

`kb/config.py::_load_env_file` 现在能覆盖 docker-compose 注入的空字符串（因为 `${VAR:-}` 会注入空串），但仍要 restart 才能让容器读到新 `.env`。

---

## 7. 已知陷阱（踩过的坑）

1. **不要在宿主机直接跑 `sync-anythingllm`**，docker 主机名 `anythingllm` 解析不到。symptom：`Failed to resolve 'anythingllm'`。
2. **不要把 80 端口写死**，很多 Linux 默认被占。已改为 `${KB_WEB_PORT:-8081}`。
3. **不要让 AI 分类变成默认**，违反甲方"元数据优先"的明确意见。
4. **不要把签阅记录从 Markdown 里删掉**，会破坏 RAG 命中。
5. **不要复活 `Pratiyush/llm-wiki`**，那个项目是给 AI 编码助手会话做 wiki 的，不适用本场景。详见 `docs/ARCHITECTURE_THINKING.md` 第 1 节。
6. **不要直接暴露 `data/documents`**（旧 nginx 方案），会让用户绕过部门权限。所有下载必须走 `kb-web` 的 `/files/{doc_id}` 做权限判断。
7. **不要忘记 ALTER TABLE 幂等**：`kb/db.py::init_db` 在 catch `duplicate column` 错误，新增字段时按这个模式写。

---

## 8. 测试约定

`tests/test_smoke.py` 是当前唯一测试。3 条用例：

1. `test_import_docs_smoke` — 导入文档+元数据+签阅，验证 Markdown 内容
2. `test_kb_web_permission_smoke` — 启动 kb-web，验证未登录拒绝、登录后访问
3. `test_sync_from_anythingllm_smoke` — 验证反向扫描

**任何 PR 前必须跑通**：

```bash
python tests/test_smoke.py
# 输出 ok 才行
```

新增功能也尽量加冒烟用例。

---

## 9. 文档优先级

接手时按这个顺序读：

1. **本文件**（你正在读）
2. `docs/CHANGELOG_DEV.md` — 上一轮做了什么
3. `docs/CONFIG.md` — 配置怎么改
4. `docs/DESIGN.md` — 业务设计
5. `docs/NEXT_STEPS.md` — 下一步详细计划

参考时再查：

- `docs/ARCHITECTURE_THINKING.md` — 为什么这样设计
- `docs/IMPLEMENTATION.md` — 现有代码盘点
- `docs/OPERATIONS.md` — 运维命令清单
- `docs/HANDOFF_STEPS.md` — 极详细的实机操作（同学版本是 `docs/ME_FIRST.md`）
- `docs/REBUILD_PLAN.md` — 最初的重构提案（部分内容已过时）
- `doc/需求.md` + `E:\Others\Image` — 甲方原始输入

---

## 10. Commit / PR 风格

- 中文 commit message，简短描述意图（参考 `git log`）
- 一个改动一个 commit，不要"大杂烩"
- PR 前必须：`python tests/test_smoke.py` 通过 + 跑一次 `python -m kb.cli doctor` 看看有没有破坏

---

## 11. 你接手时的第一动作建议

```bash
cd E:\Repo\knowledge-base
git status                              # 确认工作区状态
git log --oneline -10                   # 最近改动
python tests/test_smoke.py              # 冒烟测试
python -m kb.cli doctor                 # 环境诊断
cat docs/CHANGELOG_DEV.md               # 上一轮做了什么
```

然后等用户告诉你新需求，或者读 `docs/NEXT_STEPS.md` 自己挑任务。
