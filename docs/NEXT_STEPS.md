# 后续开发计划

> 本文档回答：**开发者接下来怎么继续开发**。
> 如果你是要在 Linux 上一步步验证当前项目，请优先看：`docs/HANDOFF_STEPS.md`。
> 如果你想先了解项目当前完成度，请看：`docs/PROGRESS.md`。

## 1. 当前状态概览

项目已经完成本地知识库 MVP 的主要代码框架，当前具备：

- Python CLI 管理工具 `kbctl`。
- SQLite 本地数据模型。
- 部门、用户、文档、签阅记录的基础表结构。
- 文档批量导入。
- 文件元数据表导入。
- 签阅记录表导入。
- 事项 ID 一对多文档关联。
- 文档解析与结构化 Markdown 生成。
- 结构化浏览与权限下载服务 `kb-web`。
- AnythingLLM API 对接骨架和增量同步状态。
- AnythingLLM 用户上传文件反向同步兜底。
- Ollama AI 分类兜底。
- Docker Compose 新架构。
- 冒烟测试。

仍需继续推进：

1. **AnythingLLM 实机 API 对接验证**。
2. **kb-web 在真实 AnythingLLM 登录下的验证**。
3. **AnythingLLM 用户上传文件后的精确同步**。
4. **来源链接从 AnythingLLM citation 跳到 kb-web 文档页**。
5. **OCR / 高级图谱 / 去重 / doctor 诊断命令等增强**。

---

## 2. 后续阶段拆分

## 阶段 A：实机验证 AnythingLLM API

### 目标

验证并修正 `kb/anythingllm.py` 中封装的 AnythingLLM API，使脚本能够真实完成：

- 创建部门 workspace。
- 创建 AnythingLLM 用户。
- 分配用户到对应 workspace。
- 上传结构化 Markdown。
- 将公共文档加入所有部门 workspace。
- 将部门文档只加入本部门 workspace。

### 为什么必须先做

AnythingLLM 的 API 版本变化较多，实际接口必须以实例上的：

```text
http://localhost:8301/api/docs
```

为准。

目前 `kb/anythingllm.py` 已经按照常见接口写了 fallback：

- `/api/v1/...`
- `/api/...`

但是仍需要实机校验。

### 执行步骤

详见：

```text
docs/HANDOFF_STEPS.md
```

最短验证命令：

```bash
docker compose up -d
python -m kb.cli init
python -m kb.cli import-users users.csv
python -m kb.cli import-docs --zone public --source ./input/files --metadata ./input/file_meta.csv --sign-records ./input/sign.csv
python -m kb.cli sync-anythingllm --skip-users
```

### 成功标准

- [ ] `sync-anythingllm` 可以无错误执行。
- [ ] 默认三个部门 workspace 自动创建。
- [ ] 用户自动创建。
- [ ] 用户自动绑定 workspace。
- [ ] 公共文档进入所有部门 workspace。
- [ ] 部门文档只进入对应部门 workspace。
- [ ] AnythingLLM 问答能引用结构化 Markdown 中的签阅记录。

### 可能需要改的代码

主要改：

```text
kb/anythingllm.py
```

如果发现 AnythingLLM 实际 API 与封装不一致，需要按 `/api/docs` 修正：

- 用户创建接口。
- workspace 创建接口。
- workspace 用户绑定接口。
- 文档上传接口。
- embedding 更新接口。

---

## 阶段 B：实机验证 kb-web 权限浏览

### 当前状态

当前已新增 `kb.web` 权限浏览服务，并在 `docker-compose.yml` 中用 `kb-web` 提供 `:80` 入口。

已实现路由：

```text
GET  /login
POST /login
GET  /logout
GET  /
GET  /documents
GET  /docs/{doc_id}
GET  /files/{doc_id}
GET  /graph
GET  /health
```

### 认证方式

认证源优先使用 AnythingLLM：

```text
POST /api/request-token
```

开发环境允许兜底：

```bash
KB_WEB_ALLOW_LOCAL_AUTH=1
```

即 AnythingLLM 不可用时，可以使用本地 `users` 表密码登录，方便开发测试。

### 授权规则

```python
if role == "admin":
    allow_all()
else:
    allow(doc.zone == "public" or doc.department == user.department)
```

### 文件下载权限

不能直接暴露 `data/documents`。

下载必须走：

```text
GET /files/{doc_id}
```

由 Web 服务检查权限后再返回文件。

### 成功标准

- [ ] 未登录用户无法访问文档列表。
- [ ] 普通用户只能看到公共区 + 本部门文档。
- [ ] 普通用户无法通过 URL 下载其他部门文件。
- [ ] 管理员可以看到全部。
- [ ] 登录认证使用 AnythingLLM 账号密码。
- [ ] AnythingLLM 不可用时，本地兜底登录可用于开发测试。

---

## 阶段 C：处理 AnythingLLM 用户上传文件的反向同步

### 背景

需求确认：

```text
用户上传文件只能通过 AnythingLLM 界面。
```

这意味着部门用户日常新增文件不一定经过我们的 `import-docs` 命令。

但是结构化浏览站点和本地文档库需要知道这些文件，因此需要从 AnythingLLM 反向同步。

### 当前状态

已实现兜底命令：

```bash
python -m kb.cli sync-from-anythingllm
```

功能：

- 默认扫描 `data/anythingllm`。
- 查找常见文档格式：PDF/DOCX/DOC/WPS/OFD/MD/TXT。
- 尝试从路径中识别部门名或 workspace slug。
- 识别不到时可用 `--default-dept` 指定。
- 复用 `import-docs` 导入本地知识库。

示例：

```bash
python -m kb.cli sync-from-anythingllm --default-dept 信息技术部
```

### 后续需要验证

实机观察：

```bash
find data/anythingllm -maxdepth 5 -type f | head -100
```

根据真实目录结构决定：

1. 继续优化目录扫描。
2. 或改为 AnythingLLM API 精确同步。

### 成功标准

- [ ] 用户通过 AnythingLLM 上传文档后，执行同步命令，本地 `documents` 能看到文件。
- [ ] 本地站点能看到该文件。
- [ ] 部门权限正确。
- [ ] 用户上传文件最终也能进入结构化浏览和下载体系。

---

## 阶段 D：来源跳转打通

### 当前状态

kb-web 文档详情和下载已实现，但 AnythingLLM 回答中的 citation 来源还没有跳转到 kb-web 文档页。

### 目标

让 AnythingLLM 回答来源能关联到：

```text
http://localhost/docs/{doc_id}
```

或：

```text
http://localhost/files/{doc_id}
```

### 可能方案

1. 在上传到 AnythingLLM 的 Markdown 中写入 kb-web 链接。
2. 在 Markdown frontmatter 或正文中包含 `doc_id` 和 `source_url`。
3. 如果 AnythingLLM 支持 metadata，则上传时携带文档 URL。
4. 如果 AnythingLLM citation 只显示文档名，则保证文档标题可在 kb-web 中搜索定位。

### 成功标准

- [ ] AnythingLLM 回答来源能对应到 kb-web 文档详情。
- [ ] 用户能从来源下载原文件。
- [ ] 权限仍由 kb-web 控制。

---

## 阶段 E：OCR 支持

### 背景

政府/企业公文 PDF 很可能是扫描件。`pypdf` 对扫描 PDF 无法提取正文。

### 目标

当 PDF 文本为空时，自动走 OCR。

### 可选方案

1. PaddleOCR
2. Tesseract OCR
3. MinerU / marker 等文档解析工具

### 推荐

MVP 后优先尝试 PaddleOCR，中文效果更好。

### 成功标准

- [ ] 扫描 PDF 可以提取中文正文。
- [ ] OCR 结果进入 Markdown。
- [ ] OCR 失败不会阻断整个批次。

---

## 阶段 F：增量更新、去重与缓存

### 当前问题

每次导入和解析大批文档时，可能重复解析；签阅记录重复导入也可能重复插入。

### 目标

基于 checksum 实现增量更新：

- 文件未变化：跳过解析。
- 元数据变化：只更新 Markdown。
- 签阅记录变化：只更新 Markdown 和 AnythingLLM embedding。
- 签阅记录重复导入时不产生重复记录。

### 成功标准

- [ ] 重复导入相同文件不会重复处理。
- [ ] 修改签阅表后能更新对应文档。
- [ ] 同步 AnythingLLM 时只同步变化文档。
- [ ] 签阅记录不重复。

---

## 阶段 G：doctor 诊断命令

### 目标

新增：

```bash
python -m kb.cli doctor
```

用于快速诊断环境。

### 检查项

- 配置文件是否存在。
- SQLite 是否可用。
- 默认部门是否存在。
- `.env` 是否有 API Key。
- Ollama 是否可访问。
- AnythingLLM 是否可访问。
- `docker-compose.yml` 是否存在。
- 当前文档数量。
- 当前用户数量。
- AnythingLLM `/api/docs` 是否可访问。

### 成功标准

- [ ] 输出清晰的成功/失败检查项。
- [ ] 遇到失败给出下一步建议。

---

## 3. 推荐近期执行顺序

最推荐的顺序：

```text
1. 按 docs/HANDOFF_STEPS.md 跑 Docker 实机验证
2. 修正 kb/anythingllm.py 的 API 适配
3. 实机验证 kb-web 权限浏览
4. 观察 data/anythingllm，完善 sync-from-anythingllm
5. 打通 AnythingLLM citation 到 kb-web 文档页
6. 增加 doctor 诊断命令
7. 增加签阅记录去重和增量缓存
8. 增加 OCR
9. 增强知识图谱可视化
```

---

## 4. 建议后续 commit 拆分

建议不要一个 commit 做完所有内容，后续按以下 commit 拆：

```text
1. 修正 AnythingLLM API 同步
2. 验证并完善 kb-web 权限浏览
3. 支持 AnythingLLM 上传文件精确反向同步
4. 打通 AnythingLLM 来源链接到 kb-web
5. 增加 doctor 诊断命令
6. 增加签阅记录去重和增量缓存
7. 增加 OCR 支持
8. 增强知识图谱可视化
```
