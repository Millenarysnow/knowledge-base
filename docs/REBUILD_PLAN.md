# 智能知识库重构计划

> 日期：2026-05-13
> 目标：基于原始需求重构本地化智能知识库，抛弃当前错误的 `llmwiki` 调用方式，做成可部署、可脚本化管理、按部门权限隔离的知识库系统。

## 1. 已确认的关键需求

### 1.1 权限

- 智能问答边界：公共区 + 用户所属部门区。
- 结构化浏览/下载也需要权限隔离：普通用户只能看公共区 + 本部门；管理员可看全部。
- 用户认证使用 AnythingLLM 自带用户体系。

### 1.2 上传与导入

- 部门用户上传文件只能通过 AnythingLLM 界面。
- 文件元数据表、签阅记录表和文件是一批一起导入。
- 一个事项 ID 可能关联多个文件。
- 签阅记录必须参与智能问答。
- 交付形式：docker-compose + 配置 + 脚本。

### 1.3 分类优先级

```text
元数据表分类 > 目录分类 > 文件名/内容/AI 分类
```

### 1.4 元数据格式

文件元数据表：

```csv
文件标识,文件标题,文件类型,文件名,文件事项ID,文件字号,文件流水号
7acf3850-4b7a-11f1-8da1-fa163e4c1d80,关于安全生产的通知,行政,7acf3850-4b7a-11f1-8da1-fa163e4c1d80.pdf,sDKC3sDU,通知（10）号,20260512
```

签阅记录表：

```csv
事项id,签阅人,签阅时间,签阅意见
sDKC3sDU,张三,2026/5/12 7:11,已阅
sDKC3sDU,李四,2026/5/12 11:11,同意
```

关联规则：

```text
文件元数据.文件事项ID = 签阅记录.事项id
```

## 2. 新架构

```text
Ollama
  - 本地 LLM
  - 本地 Embedding

AnythingLLM
  - 用户认证
  - 部门 workspace
  - 部门用户通过界面上传
  - 智能问答/RAG

KB Worker / kbctl
  - 部门/用户初始化脚本
  - 文档批量导入
  - 元数据与签阅记录绑定
  - 文档解析
  - 结构化 Markdown 生成
  - AnythingLLM API 同步
  - 静态站点生成

Nginx
  - 结构化浏览入口
  - 原文件下载入口
```

> 注意：需求里说的 “LLM Wiki” 不是继续强行使用 Pratiyush/llm-wiki，而是实现它表达的能力：结构化 Markdown、静态站点、知识图谱。

## 3. 目录结构

```text
knowledge-base/
├── docker-compose.yml
├── .env
├── config/
│   └── config.yaml
├── kb/
│   ├── cli.py
│   ├── config.py
│   ├── db.py
│   ├── import_docs.py
│   ├── import_users.py
│   ├── parser.py
│   ├── site_builder.py
│   ├── anythingllm.py
│   └── util.py
├── scripts/
│   ├── kbctl.sh
│   ├── install.sh
│   └── update-kb.sh
├── data/
│   ├── documents/
│   ├── raw/
│   ├── wiki/
│   ├── site/
│   └── db/
└── docs/
    ├── REQUIREMENTS.md
    ├── DESIGN.md
    └── OPERATIONS.md
```

## 4. 数据模型

使用 SQLite 保存结构化数据。

### departments

| 字段 | 说明 |
|---|---|
| id | 主键 |
| name | 部门名 |
| slug | workspace slug |
| created_at | 创建时间 |

### users

| 字段 | 说明 |
|---|---|
| id | 主键 |
| department | 部门 |
| username | 用户名 |
| password | 初始化密码，仅用于导入，不长期展示 |
| role | admin/member |
| anythingllm_user_id | AnythingLLM 用户 ID |

### documents

| 字段 | 说明 |
|---|---|
| id | 主键 |
| zone | public/dept |
| department | 部门名，公共区为空 |
| file_identifier | 文件标识 |
| title | 文件标题 |
| category | 分类 |
| original_filename | 原始文件名 |
| stored_path | 本地存储路径 |
| wiki_path | 结构化 markdown 路径 |
| item_id | 文件事项ID |
| doc_number | 文件字号 |
| serial_number | 文件流水号 |
| imported_at | 导入时间 |
| checksum | 文件哈希 |
| synced_to_anythingllm | 是否已同步 |

### sign_records

| 字段 | 说明 |
|---|---|
| id | 主键 |
| item_id | 事项ID |
| signer | 签阅人 |
| sign_time | 签阅时间 |
| opinion | 签阅意见 |

## 5. CLI 命令设计

```bash
# 初始化目录、数据库、默认部门
python -m kb.cli init

# 创建部门
python -m kb.cli create-dept 信息技术部

# 导入用户并同步 AnythingLLM
python -m kb.cli import-users users.csv

# 导入公共区文档，带元数据和签阅记录
python -m kb.cli import-docs \
  --zone public \
  --source ./input/files \
  --metadata ./input/file_meta.csv \
  --sign-records ./input/sign_records.csv

# 导入部门文档
python -m kb.cli import-docs \
  --zone dept \
  --dept 信息技术部 \
  --source ./input/files \
  --metadata ./input/file_meta.csv \
  --sign-records ./input/sign_records.csv

# 构建结构化浏览站点
python -m kb.cli build-site

# 同步 AnythingLLM 文档索引
python -m kb.cli sync-anythingllm

# 全量更新
python -m kb.cli update

# 状态检查
python -m kb.cli status
```

## 6. 开发阶段

### 阶段 1：打基础

- 写需求文档、设计文档。
- 建立 Python 包和 CLI。
- 建立配置、SQLite 数据库。
- 实现部门/用户/文档表。

### 阶段 2：文档导入与元数据绑定

- 支持 CSV/Excel 元数据表。
- 支持 CSV/Excel 签阅记录表。
- 支持元数据表分类优先。
- 支持事项 ID 一对多文件。
- 按 `YYYY/MM/DD/分类/文件` 落盘。

### 阶段 3：文档解析与结构化 Markdown

- PDF / DOCX / DOC / WPS / OFD / MD / TXT 转文本。
- 合并文件元数据、签阅记录、正文。
- 生成 wiki markdown。
- 签阅记录写入 markdown，确保进入问答上下文。

### 阶段 4：静态站点

- 首页。
- 登录说明/权限说明。
- 按区域、部门、日期、分类浏览。
- 文档详情页。
- 签阅记录展示。
- 原文件下载链接。
- 基础相关文档图谱。

### 阶段 5：AnythingLLM 集成

- 自动创建 workspace。
- 导入用户。
- 分配 workspace。
- 同步结构化 markdown 到 workspace。
- 公共文档同步到所有部门 workspace。
- 部门文档只同步到本部门 workspace。
- 验证 AnythingLLM GUI 上传方案。

### 阶段 6：部署与验收

- docker-compose。
- install.sh。
- update-kb.sh。
- README。
- Linux 实测。

## 7. 风险点

1. AnythingLLM API 版本变化较多，需要以 `/api/docs` 为准。
2. AnythingLLM GUI 上传后的文件如何被我们的静态站点感知，需要实测；如果 API/目录可监控则做定时同步。
3. 静态站点权限如果直接用 Nginx 很难细粒度鉴权，可能需要加一个轻量 Web 服务反代，MVP 可先生成按用户/部门访问的入口说明，最终要接 AnythingLLM 或自研 token。
4. DOC/WPS/OFD 解析依赖 LibreOffice，对 Linux 环境要求较高。
5. 大规模文档需要缓存和增量更新。

## 8. 近期执行顺序

当前先完成：

1. 文档与设计沉淀。
2. Python CLI 骨架。
3. 配置和数据库初始化。
4. 导入元数据/签阅记录/文档。
5. 生成结构化 Markdown 和基础站点。

AnythingLLM API 同步放在 CLI 骨架之后开始做，边查边对接。
