# 当前进度总览

> 本文档用于给人或后续 Agent 快速理解：当前项目到哪一步了、哪些完成了、哪些还没完成。
> 当前分支：`feature/Claude优化`
> 当前最新核心提交：`1218bf4 增强同步能力与AI分类兜底`

---

## 1. 一句话状态

当前项目已经完成了**本地知识库 MVP 的主要代码框架**：

- 批量导入。
- 元数据绑定。
- 签阅记录关联。
- 结构化 Markdown。
- 权限浏览服务。
- AnythingLLM 同步骨架。
- AI 分类兜底。
- 用户上传文件反向同步兜底。

但还没有完成最终交付闭环，因为仍需在真实 Docker + AnythingLLM 环境中验证：

- AnythingLLM API 是否完全匹配。
- workspace 是否能自动创建。
- 用户是否能自动创建和分配 workspace。
- 文档是否能真实进入 AnythingLLM embedding。
- AnythingLLM 问答是否能命中签阅记录。
- 用户通过 AnythingLLM 上传文件后的真实目录/API 行为。

---

## 2. 已完成内容

### 2.1 架构重构

已从旧的错误 `llmwiki` 思路重构为：

```text
Ollama + AnythingLLM + kbctl/KB Worker + kb-web
```

说明：原需求中的 “LLM Wiki” 被实现为本项目自己的结构化 Markdown、浏览站点和知识图谱能力，不再强依赖 Pratiyush/llm-wiki。

---

### 2.2 配置与部署

已完成：

- 新版 `docker-compose.yml`。
- 旧 compose 备份为 `docker-compose.legacy.yml`。
- `.env` 保留当前测试配置。
- `.env.example` 提供模板。
- `config/config.yaml` 配置路径、部门、分类、模型、AnythingLLM 地址。

当前服务设计：

```text
kb-ollama       :11434
kb-anythingllm  :8301
kb-worker       内部 worker
kb-web          :80
```

---

### 2.3 CLI

主入口：

```bash
python -m kb.cli
```

支持：

```text
init
status
create-dept
import-users
import-docs
build-site
sync-anythingllm
sync-from-anythingllm
update
```

---

### 2.4 部门与用户

已完成：

- 默认部门：信息技术部、办公室、研究室。
- 部门创建。
- CSV/Excel 用户导入到本地 SQLite。
- 本地 users 表记录用户、部门、角色、密码。
- AnythingLLM 用户同步代码已写，但未实机验证。

---

### 2.5 文档导入

已完成：

- 公共区导入。
- 部门区导入。
- 文件 + 元数据表 + 签阅记录表同批导入。
- 支持 PDF/DOCX/DOC/WPS/OFD/MD/TXT。
- DOC/WPS/OFD 通过 LibreOffice 转 PDF 再解析，需 Linux 实机验证。

目录结构：

```text
data/documents/public/YYYY/MM/DD/分类/文件
data/documents/dept-部门/YYYY/MM/DD/分类/文件
```

---

### 2.6 元数据表

支持字段：

```text
文件标识
文件标题
文件类型
文件名
文件事项ID
文件字号
文件流水号
```

用途：

- 文件名/文件标识匹配。
- 提供真实标题。
- 提供分类。
- 提供事项ID。
- 提供字号、流水号。

---

### 2.7 签阅记录表

支持字段：

```text
事项id
签阅人
签阅时间
签阅意见
```

关联规则：

```text
文件元数据.文件事项ID = 签阅记录.事项id
```

支持：

```text
一个事项ID -> 多个文件
一个事项ID -> 多条签阅记录
```

签阅记录会写入结构化 Markdown，因此理论上可进入 AnythingLLM RAG 上下文。

---

### 2.8 分类

已实现完整优先级：

```text
元数据表分类 > 目录分类 > 文件名/内容关键词分类 > AI 分类 > 未分类
```

AI 分类通过 Ollama 兜底执行。Ollama 不可用时自动退化为未分类，不阻断导入。

---

### 2.9 结构化 Markdown

导入后生成：

```text
data/wiki/...
```

Markdown 包含：

- frontmatter。
- 文件信息表。
- 签阅记录表。
- 正文。
- 原文件链接。

---

### 2.10 浏览与下载

已实现 `kb-web`：

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

权限规则：

```text
admin：全部
普通用户：公共区 + 本部门
```

认证：

1. 优先调用 AnythingLLM `/api/request-token`。
2. 开发环境 `KB_WEB_ALLOW_LOCAL_AUTH=1` 时，允许本地 users 表密码兜底。

下载必须走：

```text
/files/{doc_id}
```

由 `kb-web` 检查权限。

---

### 2.11 AnythingLLM 同步

已写代码：

```bash
python -m kb.cli sync-anythingllm
```

目标：

- 创建 workspace。
- 创建用户。
- 分配用户 workspace。
- 上传结构化 Markdown。
- 公共文档加入所有部门 workspace。
- 部门文档加入本部门 workspace。
- 尽量增量同步。

状态：代码完成，未实机验证。

---

### 2.12 AnythingLLM 用户上传文件反向同步

已实现兜底扫描：

```bash
python -m kb.cli sync-from-anythingllm
```

默认扫描：

```text
data/anythingllm
```

尝试通过路径中的部门名或 workspace slug 判断部门。

也支持：

```bash
python -m kb.cli sync-from-anythingllm --default-dept 信息技术部
```

状态：代码完成，需根据真实 AnythingLLM 存储结构调整。

---

### 2.13 测试

已扩展冒烟测试：

```bash
python tests/test_smoke.py
```

覆盖：

- 初始化。
- 文档 + 元数据 + 签阅记录导入。
- Markdown 生成。
- 站点生成。
- kb-web 本地兜底登录和文档访问。
- sync-from-anythingllm 保守扫描导入。

当前测试通过：

```text
ok
```

---

## 3. 未完成内容

### 3.1 AnythingLLM 实机 API 适配

未完成原因：必须等 AnythingLLM 真实跑起来，看 `/api/docs`。

待验证：

- 创建 workspace 接口。
- 创建用户接口。
- 分配用户 workspace 接口。
- 上传文档接口。
- update embeddings 接口。

主要修改点：

```text
kb/anythingllm.py
```

---

### 3.2 真实问答隔离验证

需要验证：

```text
用户可问答范围 = public + 本部门
```

目前只是代码层面的 workspace 同步设计，还没确认 AnythingLLM 中真实生效。

---

### 3.3 签阅记录问答验证

需要在 AnythingLLM 中问：

```text
关于安全生产的通知谁签阅了？
```

期望命中 Markdown 中的签阅记录。

---

### 3.4 用户上传文件精确同步

当前 `sync-from-anythingllm` 是保守扫描实现。

需要观察真实目录：

```bash
find data/anythingllm -maxdepth 5 -type f | head -100
```

然后决定是否改为：

- API 精确同步。
- 或按真实目录结构精确扫描。

---

### 3.5 AnythingLLM 来源链接跳转 kb-web

目前 kb-web 的文档详情和下载已经完成，但 AnythingLLM 回答中的来源 citation 还没有改造成跳转 kb-web 文档页。

---

### 3.6 OCR

扫描 PDF 暂不支持。

后续可接：

- PaddleOCR
- Tesseract
- MinerU / marker

---

### 3.7 高级知识图谱

当前只有事项ID ↔ 文档的基础图谱。

未完成：

- 可视化图谱。
- 人员/部门/事项/文件实体图谱。
- AI 自动相关文档。

---

### 3.8 签阅记录去重

当前重复导入签阅表时，签阅记录可能重复插入。

后续应增加唯一约束或导入批次清理。

---

### 3.9 doctor 诊断命令

还未实现：

```bash
python -m kb.cli doctor
```

建议后续做，用于快速检查：

- 配置。
- 数据库。
- Docker。
- Ollama。
- AnythingLLM。
- API Key。
- 用户和文档数量。

---

## 4. 当前完成度判断

按完整业务交付：

```text
约 55% - 65%
```

按本地导入和知识库框架：

```text
约 75%
```

最大风险点：

```text
AnythingLLM 实机 API 和真实运行行为
```

---

## 5. 下一步最重要的事

不是继续盲写代码，而是让同学在真实 Linux/Docker 环境中跑：

```bash
docker compose up -d
python -m kb.cli init
python -m kb.cli import-users users.csv
python -m kb.cli import-docs --zone public --source ./input/files --metadata ./input/file_meta.csv --sign-records ./input/sign.csv
python -m kb.cli sync-anythingllm --skip-users
```

然后反馈：

- `docker ps`
- `sync-anythingllm` 输出
- `/api/docs` 中相关接口
- AnythingLLM workspace 页面截图/结果
- kb-web 登录结果
- `data/anythingllm` 目录结构

详见：

```text
docs/HANDOFF_STEPS.md
```
