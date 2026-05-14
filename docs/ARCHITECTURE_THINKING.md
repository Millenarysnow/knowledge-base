# 重构思路说明

> 本文档回答：**什么思路**。
> 目的：让后续接手的人明白为什么要这样重构，而不是继续沿用旧 README/旧脚本。

## 1. 为什么要重构

原项目最大的问题不是代码细节，而是**需求理解和技术选型方向跑偏**。

旧实现假设：

```text
Pratiyush/llm-wiki 可以直接用于企业文档知识库
```

并在 README 和脚本中写了类似：

```text
llmwiki scan + classify + compile
llmwiki export --format static
```

但实际 Pratiyush/llm-wiki 更偏向把 Claude Code、Codex、Cursor 等 AI 编码助手的会话记录转成 wiki，并不是为企业 PDF/Word 公文知识库设计的。

因此继续修旧脚本意义不大，需要按真实业务需求重新设计。

---

## 2. 真实需求的核心

根据原始对话，真实需求可以概括为：

```text
做一个本地化、脚本可管理、按部门隔离的企业文档 RAG 知识库。
```

关键不是“调用某个 llmwiki 命令”，而是实现这些能力：

1. 本地部署。
2. 公共区 + 部门区。
3. AnythingLLM 智能问答。
4. 用户通过 AnythingLLM 登录和上传。
5. 普通用户只能访问公共区 + 本部门。
6. 管理员可访问全部。
7. 文件、元数据表、签阅记录表同批导入。
8. 签阅记录和文件建立关联。
9. 签阅记录进入问答上下文。
10. 提供结构化浏览和来源下载。

---

## 3. 总体设计思路

将系统拆成四个明确职责的部分：

```text
Ollama
  只负责本地模型和 embedding。

AnythingLLM
  只负责用户体系、workspace 隔离、用户上传、RAG 问答。

KB Worker / kbctl
  负责所有业务 glue code：导入、解析、关联、生成 Markdown、生成站点、同步 AnythingLLM。

kb-web
  负责权限浏览、文档详情和原文件下载。
```

这样每个组件职责清晰，不再把所有能力强行塞给一个不存在的 `llmwiki` 流程。

---

## 4. 为什么用 Python CLI 而不是 Bash 脚本

旧项目大量使用 Bash 脚本，但这个项目后续需要做：

- CSV/Excel 解析。
- 文件名/文件标识匹配。
- 事项 ID 一对多关联。
- SQLite 数据库。
- AnythingLLM API 调用。
- 文档解析。
- Markdown 生成。
- 权限判断。

这些逻辑用 Bash 会非常脆弱。

所以重构思路是：

```text
Bash 只做薄入口，核心逻辑全部放到 Python。
```

因此保留：

```text
scripts/kbctl.sh
scripts/update-kb.sh
scripts/compile-wiki.sh 兼容入口
```

但核心在：

```text
python -m kb.cli
```

---

## 5. 为什么引入 SQLite

需求中有明显的结构化数据：

- 部门。
- 用户。
- 文档。
- 文件元数据。
- 签阅记录。
- 事项 ID。
- 同步状态。

如果只靠目录和 Markdown，很难回答：

```text
某个用户可以看哪些文档？
某个事项 ID 关联哪些文件？
某个文件有哪些签阅记录？
哪些文档还没同步 AnythingLLM？
```

所以需要一个轻量数据库。

SQLite 足够满足 MVP：

- 无需额外服务。
- 文件型数据库。
- 适合本地部署。
- 后续可迁移 PostgreSQL。

---

## 6. 为什么生成结构化 Markdown

AnythingLLM 做 RAG 时吃的是文档内容。

如果只上传原始 PDF，RAG 可能只能看到正文，看不到：

- 文件标题。
- 文件事项 ID。
- 文件字号。
- 文件流水号。
- 签阅人。
- 签阅意见。

但需求明确要求签阅记录参与问答。

因此导入时生成结构化 Markdown：

```text
文件信息 + 签阅记录 + 正文
```

然后把这个 Markdown 同步到 AnythingLLM。

这样用户问：

```text
这份文件谁签阅了？
通知（10）号是什么文件？
关于安全生产的通知李四是什么意见？
```

RAG 才能检索到相关上下文。

---

## 7. 为什么分类优先级这样设计

需求方明确说过：

```text
文件名可能很随意，按名字分类会比较模糊。
如果不行，可以提供 CSV 模板，导入时就给好分类。
```

所以分类不能以 AI 猜测为主。

正确顺序：

```text
元数据表分类 > 目录分类 > 文件名/内容关键词分类 > AI 分类 > 未分类
```

解释：

1. 元数据表是上游系统给出的正式字段，可信度最高。
2. 目录分类通常是人工整理结果，可信度次高。
3. 文件名/内容关键词只是启发式。
4. AI 分类可能不稳定，只能兜底。
5. 实在无法判断就进入未分类，避免乱分。

---

## 8. 为什么用部门 workspace 做问答隔离

需求确认：

```text
用户问答边界 = 公共区 + 本部门
```

AnythingLLM 的天然隔离单元是 workspace。

因此设计为：

```text
信息技术部 workspace = 公共文档 + 信息技术部文档
办公室 workspace = 公共文档 + 办公室文档
研究室 workspace = 公共文档 + 研究室文档
```

公共文档导入后同步到所有部门 workspace。
部门文档导入后只同步到对应部门 workspace。

这样隔离发生在 RAG 检索层，而不是 UI 层。

---

## 9. 为什么用户认证用 AnythingLLM

需求确认：

```text
用户认证使用 AnythingLLM。
```

因此不要另起一套独立用户体系作为主认证。

当前本地 `users` 表的作用不是取代 AnythingLLM，而是保存业务映射：

```text
username -> department -> role
```

AnythingLLM 负责校验账号密码。
本地库负责判断用户属于哪个部门、能看哪些文档。

kb-web 登录时优先调用：

```text
POST /api/request-token
```

如果 AnythingLLM 返回有效 token，再查本地用户表授权。

开发阶段为了降低调试难度，允许设置：

```bash
KB_WEB_ALLOW_LOCAL_AUTH=1
```

这样 AnythingLLM 不可用时，也可以用本地 users 表密码登录。

---

## 10. 为什么仍保留静态站点生成

结构化浏览是明确需求。

虽然当前 `:80` 已由 `kb-web` 提供权限浏览，但静态站点生成仍然保留，原因是：

- 便于调试文档导入结果。
- 便于管理员检查结构化 Markdown 渲染效果。
- 便于后续做搜索索引和图谱。
- 可以作为未来前端页面的数据/模板参考。

静态站点输出目录：

```text
data/site
```

但最终用户访问应走：

```text
kb-web
```

而不是直接暴露静态 `/files/`。

---

## 11. 为什么做 kb-web

需求确认：

```text
普通用户浏览也只能看公共区 + 本部门。
管理员看全部。
```

Nginx 直接暴露：

```text
/files/...
```

会导致用户猜路径下载其他部门文档。

所以下载必须经过权限判断。

当前已实现 `kb.web`：

```text
GET /documents
GET /docs/{id}
GET /files/{id}
```

访问时检查：

```python
if role == "admin":
    allow
elif doc.zone == "public":
    allow
elif doc.department == user.department:
    allow
else:
    deny
```

---

## 12. 为什么 AnythingLLM 用户上传会有反向同步问题

需求确认：

```text
用户上传文件只能通过 AnythingLLM。
```

这意味着有一类文件不会经过我们的：

```text
python -m kb.cli import-docs
```

而是直接进入 AnythingLLM 的内部存储。

如果不处理，结构化浏览站点不会知道这些文件。

所以需要：

```text
sync-from-anythingllm
```

当前已实现兜底扫描：

```bash
python -m kb.cli sync-from-anythingllm
```

默认扫描：

```text
data/anythingllm
```

实机验证后，如果 AnythingLLM API 提供更精确的文档列表/下载接口，应优先改为 API 精确同步。

---

## 13. 为什么要做 AI 分类兜底

需求方担心文件名随意，分类不准；同时也说可以通过 CSV 模板给分类。

因此 AI 分类不能覆盖人工/元数据分类，只能兜底：

```text
元数据表分类 > 目录分类 > 文件名/内容关键词分类 > AI 分类 > 未分类
```

当前已接入 Ollama：

- Ollama 可用时，尝试用模型分类。
- Ollama 不可用时，不阻断导入，落入未分类。

---

## 14. 为什么先做 MVP，不一次做完全部

这个项目风险主要在外部组件：

- AnythingLLM API 版本不稳定。
- AnythingLLM 用户上传存储结构需要实测。
- DOC/WPS/OFD 解析依赖 LibreOffice。
- 扫描 PDF 需要 OCR。
- 来源 citation 跳转需要看 AnythingLLM 支持情况。

因此开发策略是：

```text
先打通管理员批量导入 -> 结构化 Markdown -> AnythingLLM 同步 -> 权限浏览
再补用户上传反向同步
再补来源跳转、OCR、缓存、图谱
```

这样每一步都有可验证产物，不会一口气做成不可调试的大泥球。

---

## 15. 当前架构原则

### 15.1 配置优先

分类、路径、模型、部门都放配置文件。

### 15.2 元数据优先

上游表格给的信息优先级最高。

### 15.3 脚本管理

管理员批量操作必须脚本化。

### 15.4 用户体验复用 AnythingLLM

普通用户问答和上传尽量复用 AnythingLLM。

### 15.5 权限必须在数据访问层控制

不能只靠 UI 隐藏。

### 15.6 文档内容可追溯

问答答案必须能追溯来源文件。

---

## 16. 最终目标形态

最终系统应该是：

```text
管理员：
  - 用脚本导入部门/用户
  - 用脚本导入文件+元数据+签阅记录
  - 用脚本同步 AnythingLLM
  - 用脚本重建站点

普通用户：
  - 登录 AnythingLLM
  - 在本部门 workspace 问答
  - 通过 AnythingLLM 上传本部门文件
  - 在浏览站点查看公共区+本部门文档

管理员用户：
  - 可查看所有部门文档
  - 可检查同步状态
  - 可下载所有原文件
```

---

## 17. 一句话总结

本次重构的核心思路是：

```text
把 AnythingLLM 当作认证、上传和 RAG 引擎；把 Ollama 当作本地模型服务；自己实现企业文档知识库真正需要的导入、元数据绑定、签阅记录关联、结构化 Markdown、浏览权限和同步逻辑。
```
