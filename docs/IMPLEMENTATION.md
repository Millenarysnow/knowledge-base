# 当前已开发内容说明

> 本文档回答：**你都开发了什么**。
> 当前基础提交：`2bc3d19 重构智能知识库基础架构`

## 1. 总览

本轮重构不是在旧脚本上小修小补，而是重新搭了一套面向真实需求的基础架构。

核心变化：

1. 不再强依赖错误理解下的 Pratiyush/llm-wiki。
2. 新增 Python CLI `kbctl` 作为主入口。
3. 使用 SQLite 管理部门、用户、文档、签阅记录。
4. 支持文件 + 元数据表 + 签阅记录表同批导入。
5. 支持事项 ID 一对多文件。
6. 生成结构化 Markdown，使签阅记录进入 RAG 上下文。
7. 生成结构化浏览站点。
8. 初步封装 AnythingLLM API。
9. 新增技术文档、运维文档、重构计划和冒烟测试。

---

## 2. 修改/新增的主要文件

## 2.1 README

### 文件

```text
README.md
```

### 内容

新的 README 现在描述的是重构后的真实系统：

- AnythingLLM + Ollama + KB Worker + Nginx。
- 公共区 + 部门区。
- 文件元数据表。
- 签阅记录表。
- 批量导入命令。
- 构建结构化站点命令。
- 同步 AnythingLLM 命令。
- 权限模型。
- 测试命令。

原 README 中那些不可靠的 `llmwiki scan/classify/export` 说法已经移除。

---

## 2.2 Docker Compose

### 文件

```text
docker-compose.yml
docker-compose.legacy.yml
```

### 内容

新的 `docker-compose.yml` 包含：

```text
ollama
anythingllm
kb-worker
nginx
```

旧的 docker-compose 被保留为：

```text
docker-compose.legacy.yml
```

这是为了后续如果需要对照旧实现，还能找回来。

---

## 2.3 配置文件

### 文件

```text
config/config.yaml
```

### 内容

配置包括：

- 应用名称。
- 默认语言。
- 路径配置。
- 默认部门。
- 分类字典。
- Ollama 模型。
- AnythingLLM 地址。
- AnythingLLM API Key 环境变量名。

默认部门：

```text
信息技术部
办公室
研究室
```

默认分类：

```text
行政
技术
会议
报告
```

---

## 2.4 环境变量模板

### 文件

```text
.env
.env.example
```

### 内容

当前 `.env` 简化为：

```bash
OLLAMA_MODEL=qwen2.5:7b
EMBEDDING_MODEL=bge-m3
ANYTHINGLLM_API_KEY=
```

`.env.example` 用于部署参考。

---

## 2.5 Python 包

新增目录：

```text
kb/
```

### 2.5.1 `kb/cli.py`

CLI 主入口。

支持命令：

```bash
python -m kb.cli init
python -m kb.cli status
python -m kb.cli create-dept 信息技术部
python -m kb.cli import-users users.csv
python -m kb.cli import-docs --zone public --source ./files --metadata ./meta.csv --sign-records ./sign.csv
python -m kb.cli import-docs --zone dept --dept 信息技术部 --source ./files --metadata ./meta.csv --sign-records ./sign.csv
python -m kb.cli build-site
python -m kb.cli sync-anythingllm
python -m kb.cli sync-anythingllm --skip-users
python -m kb.cli update
```

### 2.5.2 `kb/config.py`

负责：

- 加载 `config/config.yaml`。
- 解析项目路径。
- 创建必要目录。
- 标准化分类。
- 生成部门 workspace slug。

部门 slug 采用 md5 简短形式，例如：

```text
信息技术部 -> dept-3a9507ef
办公室 -> dept-93cfc1e1
研究室 -> dept-bf49d0f4
```

这样避免中文 slug 在不同系统/API 中出现兼容问题。

### 2.5.3 `kb/db.py`

负责 SQLite 数据库。

表：

```text
departments
users
documents
sign_records
sync_log
```

已实现：

- 初始化 schema。
- upsert department。
- upsert user。
- upsert document。
- insert sign record。
- 查询部门。
- 查询文档。

### 2.5.4 `kb/util.py`

通用工具：

- CSV 读取。
- Excel 读取。
- 表格字段标准化。
- 文件哈希。
- 安全文件名。
- Markdown 转义。
- 文件复制。

### 2.5.5 `kb/parser.py`

文档解析。

支持：

| 格式 | 解析方式 |
|---|---|
| PDF | pypdf |
| DOCX | python-docx |
| DOC | LibreOffice 转 PDF 再解析 |
| WPS | LibreOffice 转 PDF 再解析 |
| OFD | LibreOffice 转 PDF 再解析 |
| MD | 直接读取 |
| TXT | 直接读取，兼容 utf-8/gbk/gb18030 |

### 2.5.6 `kb/import_users.py`

用户/部门导入。

兼容当前仓库里的 `users.csv` 格式：

```csv
type,dept_name,username,password,role
```

导入到本地 SQLite。

### 2.5.7 `kb/import_docs.py`

文档导入核心逻辑。

功能：

- 读取文件元数据表。
- 读取签阅记录表。
- 文件名/文件标识匹配元数据。
- 事项 ID 关联签阅记录。
- 支持事项 ID 一对多文件。
- 解析文件正文。
- 按分类优先级确定分类。
- 按 `YYYY/MM/DD/分类/文件` 落盘。
- 生成 raw 文本。
- 生成 wiki Markdown。
- 写入 SQLite。

分类优先级：

```text
元数据表分类 > 目录分类 > 文件名/内容关键词分类 > AI 分类 > 未分类
```

### 2.5.8 `kb/site_builder.py`

结构化浏览站点生成器。

生成：

```text
data/site/index.html
data/site/documents.html
data/site/docs/{id}.html
data/site/graph.html
data/site/search-index.json
```

文档详情页包含：

- 文件标题。
- 分类。
- 所属区域。
- 文件标识。
- 原始文件名。
- 文件事项 ID。
- 文件字号。
- 文件流水号。
- 签阅记录。
- 正文。
- 下载链接。

### 2.5.9 `kb/anythingllm.py`

AnythingLLM API 客户端。

已封装：

- `ensure_workspace`
- `ensure_user`
- `assign_workspace_users`
- `upload_document`
- `upload_and_embed`
- `update_embeddings`
- `sync_anythingllm`

`sync_anythingllm` 的目标：

- 为每个部门创建 workspace。
- 创建用户。
- 分配用户到 workspace。
- 上传 wiki Markdown。
- 公共文档加入所有部门 workspace。
- 部门文档加入本部门 workspace。

注意：需要实机根据 `/api/docs` 验证。

### 2.5.10 `kb/auth.py`

封装 AnythingLLM 登录认证：

```text
POST /api/request-token
GET /api/system/check-token
```

这是结构化浏览权限控制的认证基础模块。

### 2.5.11 `kb/web.py`

权限浏览服务。

提供：

```text
/login
/logout
/
/documents
/docs/{id}
/files/{id}
/graph
/health
```

认证方式：

1. 优先调用 AnythingLLM `/api/request-token`。
2. 开发环境如设置 `KB_WEB_ALLOW_LOCAL_AUTH=1`，允许本地 users 表密码兜底。

授权规则：

```text
admin：可访问全部
普通用户：公共区 + 本部门
```

文件下载通过 `/files/{id}`，会检查权限。

---

## 2.6 脚本

### `scripts/kbctl.sh`

Linux 下的 CLI 转发入口：

```bash
scripts/kbctl.sh status
scripts/kbctl.sh import-docs ...
```

### `scripts/compile-wiki.sh`

旧入口兼容脚本。

当前只保留：

```bash
scripts/compile-wiki.sh build
scripts/compile-wiki.sh status
```

旧的 import 逻辑不再建议使用。

### `scripts/update-kb.sh`

定时更新入口。

执行：

- `python3 -m kb.cli update`
- 如果配置了 `ANYTHINGLLM_API_KEY`，则尝试 `sync-anythingllm`

---

## 2.7 安装脚本

### 文件

```text
install.sh
```

### 内容

新版 `install.sh` 做：

1. 安装 Python 依赖。
2. 初始化本地数据库。
3. 提示启动 docker compose。

不再执行旧版错误的 `llmwiki` 安装和调用。

---

## 2.8 文档

### `docs/REBUILD_PLAN.md`

记录：

- 已确认需求。
- 新架构。
- 数据模型。
- CLI 命令设计。
- 开发阶段。
- 风险点。

### `docs/DESIGN.md`

记录：

- 系统设计目标。
- 系统边界。
- 组件架构。
- 权限模型。
- 数据导入流程。
- 分类策略。
- 元数据模型。
- AnythingLLM API 对接。
- 浏览权限方案。

### `docs/OPERATIONS.md`

记录：

- 环境要求。
- 启动服务。
- 初始化。
- 导入用户。
- 导入文档。
- 元数据表格式。
- 签阅记录表格式。
- 构建站点。
- 配置 AnythingLLM API Key。
- 常见问题。

### `docs/NEXT_STEPS.md`

记录：

- 后续开发计划。
- 阶段拆分。
- 每阶段目标。
- 每阶段成功标准。

### `docs/IMPLEMENTATION.md`

即本文档，记录已经开发了什么。

---

## 2.9 新增后续能力

本阶段继续补充：

- `kb/ollama.py`：封装 Ollama chat 和可用性检测。
- `kb/import_docs.py`：接入 Ollama AI 分类兜底。
- `kb/sync_from_anythingllm.py`：保守扫描 AnythingLLM 本地存储目录，将用户上传文件导入本地知识库。
- `kb/anythingllm.py`：增加同步状态落库、workspace 详情检查、增量 embedding 逻辑。
- `kb/db.py`：新增 `anythingllm_documents`、`workspace_documents` 同步状态表。
- `tests/test_smoke.py`：增加 kb-web 权限和 sync-from-anythingllm 冒烟测试。

---

## 2.10 测试

### 文件

```text
tests/test_smoke.py
```

### 测试内容

测试会：

1. 清理运行数据。
2. 初始化系统。
3. 生成一个示例文档。
4. 生成文件元数据表。
5. 生成签阅记录表。
6. 导入文档。
7. 生成结构化浏览站点。
8. 检查生成的 Markdown 包含：
   - 张三
   - 李四
   - 通知（10）号
9. 检查站点文件存在。
10. 清理运行数据。

执行：

```bash
python tests/test_smoke.py
```

当前已经执行通过。

---

## 3. 已验证内容

已经实际验证：

```bash
python -m kb.cli init
python -m kb.cli status
python tests/test_smoke.py
```

冒烟测试输出：

```text
ok
```

这说明当前以下链路可用：

```text
初始化 -> 导入文档+元数据+签阅记录 -> 生成 Markdown -> 生成站点
```

---

## 4. 尚未实机验证内容

以下内容已经写了代码骨架，但必须等 AnythingLLM 服务跑起来后验证：

- 创建 workspace。
- 创建用户。
- 用户分配 workspace。
- 上传 Markdown 到 AnythingLLM。
- 更新 workspace embedding。
- AnythingLLM 问答能否命中签阅记录。

主要相关文件：

```text
kb/anythingllm.py
```

---

## 5. 本轮提交

提交记录：

```text
2bc3d19 重构智能知识库基础架构
```

该提交包括：

- README 重写。
- Docker Compose 重构。
- Python CLI。
- SQLite 数据库。
- 导入流程。
- 文档解析。
- 站点生成。
- AnythingLLM API 骨架。
- 技术/运维/计划文档。
- 冒烟测试。
