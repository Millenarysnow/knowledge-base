# 智能知识库运维手册

## 1. 环境要求

推荐 Linux 服务器。

依赖：

- Docker
- Docker Compose v2
- Python 3.11+
- 足够磁盘空间
- 如需解析 DOC/WPS/OFD，容器内需要 LibreOffice

## 2. 启动服务

```bash
docker compose -f docker-compose.v2.yml up -d
```

访问：

```text
AnythingLLM: http://localhost:8301
权限浏览站点: http://localhost
```

`http://localhost` 由 `kb-web` 提供权限控制。

## 3. 初始化

```bash
python -m kb.cli init
```

默认创建：

```text
信息技术部
办公室
研究室
```

查看状态：

```bash
python -m kb.cli status
```

## 4. 导入用户

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

> 注意：当前命令先导入本地库；同步到 AnythingLLM 需要配置 API Key 并执行 sync-anythingllm。

## 5. 导入文档

### 5.1 公共区

```bash
python -m kb.cli import-docs \
  --zone public \
  --source ./input/files \
  --metadata ./input/file_meta.csv \
  --sign-records ./input/sign_records.csv
```

### 5.2 部门区

```bash
python -m kb.cli import-docs \
  --zone dept \
  --dept 信息技术部 \
  --source ./input/files \
  --metadata ./input/file_meta.csv \
  --sign-records ./input/sign_records.csv
```

## 6. 元数据表

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

## 7. 构建浏览站点

```bash
python -m kb.cli build-site
```

输出目录：

```text
data/site
```

Nginx 会挂载该目录。

## 8. 配置 AnythingLLM API Key

进入 AnythingLLM 管理界面创建 API Key，然后写入 `.env`：

```bash
ANYTHINGLLM_API_KEY=ANLLM-xxxx
```

同步：

```bash
python -m kb.cli sync-anythingllm
```

如失败，请访问：

```text
http://localhost:8301/api/docs
```

核对当前版本 API。

## 9. 从 AnythingLLM 同步用户上传文件

用户日常上传文件走 AnythingLLM 界面。为了让这些文件进入本地结构化浏览，可使用兜底扫描命令：

```bash
python -m kb.cli sync-from-anythingllm --default-dept 信息技术部
```

说明：

- 默认扫描 `data/anythingllm`。
- 如果路径中能识别部门名或 workspace slug，会自动归属部门。
- 如果无法识别部门，可以用 `--default-dept` 指定。
- 该实现是保守扫描，后续可根据实际 `/api/docs` 或 AnythingLLM 存储结构增强为精确同步。

## 10. 模型配置

`.env`：

```bash
OLLAMA_MODEL=qwen2.5:7b
EMBEDDING_MODEL=bge-m3
```

低配机器可使用：

```bash
OLLAMA_MODEL=qwen2.5:1.5b
```

## 11. 结构化浏览权限

浏览站点入口：

```text
http://localhost
```

登录方式：

1. 优先调用 AnythingLLM `/api/request-token` 校验账号密码。
2. 开发环境如设置 `KB_WEB_ALLOW_LOCAL_AUTH=1`，AnythingLLM 不可用时允许使用本地 `users` 表密码兜底。

权限规则：

```text
admin：可访问全部文档
普通用户：只能访问公共区 + 本部门文档
```

文件下载必须通过 `kb-web` 的 `/files/{doc_id}`，不要直接暴露 `data/documents`。

## 12. 常见问题

### 12.1 Windows 控制台输出乱码

设置：

```cmd
set PYTHONIOENCODING=utf-8
```

### 12.2 DOC/WPS/OFD 无法解析

确认 LibreOffice 可用。

### 12.3 AnythingLLM 同步失败

1. 检查 API Key。
2. 检查 AnythingLLM 地址。
3. 打开 `/api/docs` 核对接口路径。
4. 查看 `sync-anythingllm` 输出错误。

### 12.4 用户通过 AnythingLLM 上传的文件没有出现在结构化站点

这是后续需要实现的能力：从 AnythingLLM 存储目录/API 反向同步用户上传文件。
当前 MVP 主要支持管理员批量导入。
