# 智能知识库

本项目用于构建一个**本地化部署、基于 AnythingLLM + Ollama 的团队智能知识库**。

核心能力：

- 公共区 + 部门区文档管理
- AnythingLLM 用户体系与部门 workspace 隔离
- PDF / DOC / DOCX / WPS / OFD / MD / TXT 批量导入
- 文件元数据表与签阅记录表同批导入
- 签阅记录进入问答上下文
- 结构化 Markdown 生成
- 结构化浏览站点与原文件下载

> 说明：原需求中提到的 “LLM Wiki” 在这里实现为结构化 Markdown、静态站点与知识图谱能力，不再强依赖 Pratiyush/llm-wiki。

## 1. 架构

```text
Ollama
  本地 LLM / Embedding

AnythingLLM
  用户认证 / 部门 workspace / RAG 问答 / 用户上传

KB Worker / kbctl
  批量导入 / 元数据绑定 / 签阅记录绑定 / 文档解析 / 站点生成 / AnythingLLM 同步

Nginx
  结构化浏览站点 / 原文件下载
```

## 2. 快速开始

### 2.1 安装依赖

本地执行 CLI：

```bash
pip install -r requirements.txt
```

### 2.2 初始化

```bash
python -m kb.cli init
python -m kb.cli status
```

默认创建三个部门：

```text
信息技术部
办公室
研究室
```

### 2.3 启动 Docker 服务

```bash
docker compose -f docker-compose.v2.yml up -d
```

访问：

```text
AnythingLLM: http://localhost:8301
权限浏览站点: http://localhost
```

`http://localhost` 现在由 `kb-web` 提供权限控制：普通用户只能看公共区 + 本部门，管理员可看全部。

## 3. 导入用户

CSV 示例：

```csv
type,dept_name,username,password,role
dept,信息技术部,,,
user,信息技术部,zhangsan,123456,member
user,信息技术部,itadmin,123456,admin
```

导入：

```bash
python -m kb.cli import-users users.csv
```

## 4. 导入文档

### 4.1 文件元数据表

```csv
文件标识,文件标题,文件类型,文件名,文件事项ID,文件字号,文件流水号
7acf3850-4b7a-11f1-8da1-fa163e4c1d80,关于安全生产的通知,行政,7acf3850-4b7a-11f1-8da1-fa163e4c1d80.pdf,sDKC3sDU,通知（10）号,20260512
```

### 4.2 签阅记录表

```csv
事项id,签阅人,签阅时间,签阅意见
sDKC3sDU,张三,2026/5/12 7:11,已阅
sDKC3sDU,李四,2026/5/12 11:11,同意
```

### 4.3 公共区导入

```bash
python -m kb.cli import-docs \
  --zone public \
  --source ./input/files \
  --metadata ./input/file_meta.csv \
  --sign-records ./input/sign_records.csv
```

### 4.4 部门区导入

```bash
python -m kb.cli import-docs \
  --zone dept \
  --dept 信息技术部 \
  --source ./input/files \
  --metadata ./input/file_meta.csv \
  --sign-records ./input/sign_records.csv
```

## 5. 构建结构化浏览站点

```bash
python -m kb.cli build-site
```

输出目录：

```text
data/site
```

## 6. 同步 AnythingLLM

先在 AnythingLLM 管理界面创建 API Key，然后设置环境变量：

```bash
export ANYTHINGLLM_API_KEY=ANLLM-xxxx
```

Windows CMD：

```cmd
set ANYTHINGLLM_API_KEY=ANLLM-xxxx
```

同步：

```bash
python -m kb.cli sync-anythingllm
```

只同步 workspace 和文档、不创建用户：

```bash
python -m kb.cli sync-anythingllm --skip-users
```

从 AnythingLLM 本地存储目录保守扫描用户上传文件并导入本地库：

```bash
python -m kb.cli sync-from-anythingllm --default-dept 信息技术部
```

> 该命令是兜底实现，会扫描 `data/anythingllm` 下常见文档文件；实机验证后可按 AnythingLLM API/目录结构继续增强。

> AnythingLLM API 会随版本变化，如同步失败，请访问 `http://localhost:8301/api/docs` 核对接口。

## 7. 分类优先级

```text
元数据表分类 > 目录分类 > 文件名/内容关键词分类 > AI 分类 > 未分类
```

当前已实现：

```text
元数据表分类 > 目录分类 > 文件名/内容关键词分类 > AI 分类 > 未分类
```

AI 分类通过 Ollama 兜底执行；如果 Ollama 不可用，则自动退化为“未分类”。

## 8. 权限模型

- 普通用户：只能访问公共区 + 本部门。
- 管理员：可访问全部。
- 问答权限通过 AnythingLLM workspace 隔离。
- 结构化浏览权限通过 `kb-web` 控制，登录时优先使用 AnythingLLM 账号密码；开发环境允许本地 users 表密码兜底。

## 9. 开发验证

运行冒烟测试：

```bash
python tests/test_smoke.py
```

## 10. 文档

- [重构计划](docs/REBUILD_PLAN.md)
- [技术设计](docs/DESIGN.md)
- [运维手册](docs/OPERATIONS.md)
- [后续开发计划](docs/NEXT_STEPS.md)
- [已开发内容说明](docs/IMPLEMENTATION.md)
- [重构思路说明](docs/ARCHITECTURE_THINKING.md)
