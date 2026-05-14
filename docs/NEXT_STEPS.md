# 后续开发计划

> 本文档回答：**接下来怎么做**。
> 当前分支：`feature/Claude优化`
> 当前基础提交：`2bc3d19 重构智能知识库基础架构`

## 1. 当前状态概览

项目已经完成第一轮架构重构，当前已经具备：

- Python CLI 管理工具 `kbctl`。
- SQLite 本地数据模型。
- 部门、用户、文档、签阅记录的基础表结构。
- 文档批量导入。
- 文件元数据表导入。
- 签阅记录表导入。
- 事项 ID 一对多文档关联。
- 文档解析与结构化 Markdown 生成。
- 静态结构化浏览站点生成。
- AnythingLLM API 对接骨架。
- Docker Compose 新架构。
- 冒烟测试。

但还有三块核心工作需要继续推进：

1. **AnythingLLM 实机 API 对接验证**。
2. **结构化浏览权限控制**。
3. **AnythingLLM 用户上传文件后的反向同步**。

这三块完成后，项目才算进入可交付 MVP。

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

AnythingLLM 的 API 版本变化较多，文档里也明确说明应以实例上的：

```text
http://localhost:8301/api/docs
```

为准。

目前 `kb/anythingllm.py` 已经按照常见接口写了 fallback：

- `/api/v1/...`
- `/api/...`

但是仍需要实机校验。

### 执行步骤

#### 1. 启动服务

```bash
docker compose up -d
```

#### 2. 查看容器状态

```bash
docker ps
```

确认至少有：

```text
kb-ollama
kb-anythingllm
kb-worker
kb-nginx
```

#### 3. 打开 AnythingLLM

```text
http://localhost:8301
```

完成首次初始化。

#### 4. 创建 AnythingLLM API Key

在 AnythingLLM 管理页面中创建 API Key。

先测Linux

然后写入 `.env`：

```bash
ANYTHINGLLM_API_KEY=3WQYGVA-90P46DK-N453FQJ-RMKWSR4
```

Windows CMD 临时设置：

```cmd
set ANYTHINGLLM_API_KEY=ANLLM-xxxx
```

Linux/macOS 临时设置：

```bash
export ANYTHINGLLM_API_KEY=3WQYGVA-90P46DK-N453FQJ-RMKWSR4
```

#### 5. 初始化本地库

```bash
python -m kb.cli init
```

#### 6. 导入用户

```bash
python -m kb.cli import-users users.csv
```

#### 7. 准备一组测试文档

建议构造：

```text
input/
├── files/
│   └── 2026/05/12/7acf3850-4b7a-11f1-8da1-fa163e4c1d80.pdf
├── file_meta.csv
└── sign.csv
```

#### 8. 导入测试文档

```bash
python -m kb.cli import-docs \
  --zone public \
  --source ./input/files \
  --metadata ./input/file_meta.csv \
  --sign-records ./input/sign.csv
```

#### 9. 同步 AnythingLLM

```bash
python -m kb.cli sync-anythingllm
```

如果用户同步接口失败，可先跳过用户，只验证 workspace + 文档：

```bash
python -m kb.cli sync-anythingllm --skip-users
```

#### 10. 核对 AnythingLLM 中的 workspace 和文档

打开：

```text
http://localhost:8301
```

检查：

- 是否存在信息技术部、办公室、研究室对应 workspace。
- 公共文档是否被加入所有部门 workspace。
- 部门文档是否只在对应部门 workspace。
- 用户是否可以登录。
- 用户是否只看到自己部门 workspace。

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

## 阶段 B：实现结构化浏览权限控制

### 目标

你已经确认：

```text
普通用户只能浏览公共区 + 本部门；管理员可以浏览全部。
```

当前站点是静态 HTML，由 Nginx 直接托管。静态站点无法识别当前用户身份，所以不满足最终权限需求。

### 建议方案

新增轻量 Web 服务：

```text
kb/web.py
```

或者：

```text
kb/web_app.py
```

推荐使用 FastAPI。

### 认证方式

认证源仍然使用 AnythingLLM：

```text
POST /api/request-token
```

用户在 KB Web 登录页输入 AnythingLLM 账号密码。KB Web 调 AnythingLLM 校验，如果成功，再在本地 `users` 表查：

- 用户所属部门。
- 用户角色。

### 授权规则

```python
if role == "admin":
    allow_all()
else:
    allow(doc.zone == "public" or doc.department == user.department)
```

### 需要实现的路由

```text
GET  /login
POST /login
POST /logout
GET  /
GET  /documents
GET  /docs/{doc_id}
GET  /files/{doc_id}
GET  /graph
GET  /health
```

### 文件下载权限

不能再用 Nginx 直接暴露：

```text
/files/...
```

否则用户可以猜路径下载其他部门文件。

下载必须走：

```text
GET /files/{doc_id}
```

由 Web 服务检查权限后再返回文件。

### Docker Compose 调整

当前是：

```text
nginx -> data/site + data/documents
```

后续可改成：

```text
kb-web :80
```

或者：

```text
nginx :80 -> reverse_proxy -> kb-web :8000
```

### 成功标准

- [ ] 未登录用户无法访问文档列表。
- [ ] 普通用户只能看到公共区 + 本部门文档。
- [ ] 普通用户无法通过 URL 下载其他部门文件。
- [ ] 管理员可以看到全部。
- [ ] 登录认证使用 AnythingLLM 账号密码。

---

## 阶段 C：处理 AnythingLLM 用户上传文件的反向同步

### 背景

你确认：

```text
用户上传文件只能通过 AnythingLLM 界面。
```

这意味着部门用户日常新增文件不一定经过我们的 `import-docs` 命令。

但是结构化浏览站点和本地文档库需要知道这些文件，因此需要从 AnythingLLM 反向同步。

### 目标

实现命令：

```bash
python -m kb.cli sync-from-anythingllm
```

功能：

1. 读取 AnythingLLM 中各 workspace 的文档列表。
2. 判断文档属于哪个部门 workspace。
3. 将用户上传文档同步到：

```text
data/documents/dept-部门/YYYY/MM/DD/分类/文件
```

4. 解析正文。
5. 生成结构化 Markdown。
6. 更新 SQLite。
7. 重建结构化浏览站点。

### 可选实现方式

#### 方式 1：通过 AnythingLLM API

如果 `/api/docs` 提供 workspace 文档列表和下载接口，则优先用 API。

优点：

- 稳定。
- 不依赖内部存储目录。

缺点：

- 需要实机确认 API 是否足够。

#### 方式 2：扫描 AnythingLLM 存储目录

AnythingLLM 容器存储挂载在：

```text
data/anythingllm
```

可以研究其文档缓存目录，扫描新增文件。

优点：

- 不依赖 API。

缺点：

- 目录结构可能随版本变化。
- 需要识别 workspace 归属。

### 推荐顺序

1. 先看 `/api/docs` 是否有可用接口。
2. 如果 API 不够，再研究存储目录。

### 成功标准

- [ ] 用户通过 AnythingLLM 上传文档后，执行同步命令，本地 `documents` 能看到文件。
- [ ] 本地站点能看到该文件。
- [ ] 部门权限正确。
- [ ] 用户上传文件最终也能进入结构化浏览和下载体系。

---

## 阶段 D：AI 分类兜底

### 当前状态

已经实现：

```text
元数据表分类 > 目录分类 > 文件名/内容关键词分类 > 未分类
```

还没有实现 AI 分类。

### 目标

接入 Ollama 作为兜底分类：

```text
文件名/内容关键词无法分类时 -> 调 Ollama 判断分类
```

### 推荐 Prompt

```text
你是一个文档分类助手。请从以下分类中选择最合适的一类：行政、技术、会议、报告。
只返回 JSON：{"category":"行政","reason":"..."}
```

### 注意

AI 分类只能作为兜底，不能覆盖元数据表分类。

### 成功标准

- [ ] 元数据表有分类时不调用 AI。
- [ ] 目录有分类时不调用 AI。
- [ ] 关键词能分类时不调用 AI。
- [ ] 只有前三者失败时才调用 AI。
- [ ] AI 分类结果写入 documents 表和 wiki Markdown。

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

## 阶段 F：增量更新与缓存

### 当前问题

每次导入和解析大批文档时，可能重复解析。

### 目标

基于 checksum 实现增量更新：

- 文件未变化：跳过解析。
- 元数据变化：只更新 Markdown。
- 签阅记录变化：只更新 Markdown 和 AnythingLLM embedding。

### 成功标准

- [ ] 重复导入相同文件不会重复处理。
- [ ] 修改签阅表后能更新对应文档。
- [ ] 同步 AnythingLLM 时只同步变化文档。

---

## 3. 推荐近期执行顺序

最推荐的顺序：

```text
1. 跑 Docker，实机验证 AnythingLLM API
2. 修正 kb/anythingllm.py
3. 实现 kb-web 权限浏览服务
4. 调整 docker-compose，将 :80 指向 kb-web
5. 实现 sync-from-anythingllm
6. 接入 Ollama AI 分类
7. 增加 OCR
8. 增量缓存和稳定性优化
```

---

## 4. 下一次开发建议拆分 commit

建议不要一个 commit 做完所有内容，后续按以下 commit 拆：

```text
1. 修正 AnythingLLM API 同步
2. 增加基于 AnythingLLM 的权限浏览服务
3. 支持 AnythingLLM 上传文件反向同步
4. 增加 Ollama AI 分类兜底
5. 增加 OCR 支持
6. 增加增量缓存和稳定性优化
```
