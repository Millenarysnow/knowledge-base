# 智能知识库技术设计

## 1. 设计目标

本系统用于本地化部署团队知识库，核心目标：

1. 将 PDF/DOC/DOCX/WPS/OFD 等团队文档导入本地知识库。
2. 支持公共区与部门区。
3. 使用 AnythingLLM 自带账号体系和 workspace 实现问答权限隔离。
4. 普通用户只能问答/浏览公共区 + 本部门；管理员可访问全部。
5. 文件元数据表和签阅记录表与文件同批导入。
6. 签阅记录进入知识库上下文，参与智能问答。
7. 提供结构化浏览站点和原文件下载。
8. 交付 docker-compose + 配置 + 脚本。

## 2. 系统边界

### 2.1 本系统负责

- 批量导入文件。
- 批量导入元数据表。
- 批量导入签阅记录表。
- 批量导入部门和用户。
- 解析文档为文本。
- 合并文件元数据、签阅记录和正文。
- 生成结构化 Markdown。
- 生成结构化浏览站点。
- 调用 AnythingLLM API 创建 workspace、上传文档、更新 embedding。

### 2.2 AnythingLLM 负责

- 用户登录认证。
- 部门用户日常上传文件。
- RAG 问答。
- workspace 级别的文档隔离。

### 2.3 不负责

- 不做公文审批流。
- 不做签阅录入页面。
- 不做领导批示流程。
- 不替代 OA 系统。

## 3. 组件架构

```text
浏览器
├── AnythingLLM :8301
│   ├── 登录认证
│   ├── 部门 workspace
│   ├── 用户上传
│   └── 智能问答
│
└── KB Web / Nginx :80
    ├── 结构化浏览
    ├── 文档详情
    └── 原文件下载

Docker Services
├── ollama
├── anythingllm
├── kb-worker
└── nginx / kb-web
```

## 4. 权限模型

### 4.1 用户角色

| 角色 | 说明 |
|---|---|
| admin | 管理员，可访问全部文档 |
| member/default | 普通用户，只能访问公共区 + 本部门 |

### 4.2 区域

| 区域 | 说明 |
|---|---|
| public | 公共区，所有部门用户可访问 |
| dept-部门名 | 部门区，仅本部门用户可访问 |

### 4.3 AnythingLLM workspace 映射

每个部门一个 workspace：

```text
信息技术部 workspace = public + 信息技术部文档
办公室 workspace = public + 办公室文档
研究室 workspace = public + 研究室文档
```

公共文档导入时，需要同步到所有部门 workspace。
部门文档导入时，只同步到该部门 workspace。

## 5. 数据导入流程

```text
文件目录 + 文件元数据表 + 签阅记录表
  ↓
读取元数据表，按文件名/文件标识匹配文件
  ↓
读取签阅记录表，按事项ID分组
  ↓
解析原文件正文
  ↓
按分类优先级确定分类
  ↓
复制到 data/documents/{public|dept-XX}/YYYY/MM/DD/分类/文件
  ↓
生成 data/raw 文本
  ↓
生成 data/wiki 结构化 Markdown
  ↓
写入 SQLite
  ↓
生成站点 / 同步 AnythingLLM
```

## 6. 分类策略

优先级：

```text
元数据表分类 > 目录分类 > 文件名/内容关键词分类 > AI 分类 > 未分类
```

当前 MVP 已实现：

```text
元数据表分类 > 目录分类 > 文件名/内容关键词分类 > 未分类
```

AI 分类后续通过 Ollama 接入。

## 7. 元数据模型

### 7.1 文件元数据表

| 字段 | 说明 |
|---|---|
| 文件标识 | 文档唯一标识，通常是 UUID |
| 文件标题 | 人类可读标题 |
| 文件类型 | 分类 |
| 文件名 | 原始文件名 |
| 文件事项ID | 与签阅记录关联的事项 ID |
| 文件字号 | 公文字号 |
| 文件流水号 | 流水号 |

### 7.2 签阅记录表

| 字段 | 说明 |
|---|---|
| 事项id | 关联文件元数据的文件事项ID |
| 签阅人 | 查阅/签阅人员 |
| 签阅时间 | 时间 |
| 签阅意见 | 已阅/同意/批示/笔记 |

### 7.3 关联关系

```text
文件元数据.文件事项ID = 签阅记录.事项id
```

一个事项 ID 可以关联多个文件。

## 8. 结构化 Markdown

每篇文档生成一个 Markdown，包含：

```text
frontmatter
文件信息表
签阅记录表
正文
```

签阅记录写入 Markdown 是为了让 AnythingLLM RAG 可以回答签阅相关问题。

## 9. AnythingLLM API 对接

### 9.1 已知常见接口

登录：

```text
POST /api/request-token
```

创建 workspace：

```text
POST /api/workspace/new
POST /api/v1/workspace/new
```

创建用户：

```text
POST /api/admin/users/new
```

绑定 workspace 用户：

```text
POST /api/admin/workspace-users
```

上传文档：

```text
POST /api/v1/document/upload
POST /api/workspace/{slug}/upload-and-embed
```

更新 embedding：

```text
POST /api/v1/workspace/{slug}/update-embeddings
POST /api/workspace/{slug}/update-embeddings
```

### 9.2 注意

AnythingLLM API 随版本变化，最终以实例上的：

```text
http://localhost:8301/api/docs
```

为准。

## 10. 浏览权限方案

你已确认结构化浏览也需要权限：

- 普通用户：公共区 + 本部门。
- 管理员：全部。

纯 Nginx 静态站点无法识别 AnythingLLM 登录用户，因此后续需要二选一：

### 方案 A：轻量 KB Web

实现一个 FastAPI/Flask Web 服务：

- 使用 AnythingLLM `/api/request-token` 做登录代理。
- 本地记录 username -> department/role。
- 访问文档时按本地权限过滤。
- 下载文件时也检查权限。

优点：实现可控。
缺点：严格来说多了一个登录页，但认证源仍然是 AnythingLLM。

### 方案 B：前置网关鉴权

用 Nginx auth_request 或企业统一认证。

优点：架构更规范。
缺点：初期复杂。

MVP 暂时生成静态站点，后续补 KB Web。

## 11. 风险

1. AnythingLLM API 需要实机验证。
2. AnythingLLM GUI 上传后的文件同步到本地站点，需要研究存储结构或 API。
3. 扫描 PDF 需要 OCR，当前暂未实现。
4. DOC/WPS/OFD 依赖 LibreOffice。
5. 大规模文档需要缓存、批处理和失败重试。
