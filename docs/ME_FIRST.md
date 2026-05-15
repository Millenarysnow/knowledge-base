# 同学，看这一份就够了

> 这是给你（项目维护者）的入口文档。当前打开仓库后**只需要看这份**，按顺序做就能完成今晚的实机验证。
> 如果某一步出错，把出错那一步的输出原样回传给我（或下一个 agent），不要自己强改代码。

---

## 1. 30 秒了解项目

本地化的企业智能知识库，给团队做按部门隔离的 RAG 问答 + 文档浏览。

```text
Ollama          本地 LLM + Embedding
AnythingLLM     用户认证 / workspace 隔离 / 用户上传 / RAG 问答
kb (Python)     批量导入 / 元数据&签阅记录绑定 / 解析 / 结构化 Markdown / 同步 AnythingLLM
kb-web          按部门权限的浏览与下载
```

需求来源：`doc/需求.md`、`E:\Others\Image` 下的微信对话截图（如果不在你机器上不必看，关键点已沉淀进 `docs/DESIGN.md`）。

---

## 2. 当前进度一句话

代码框架完成约 **65%**，本地冒烟测试通过；但 **AnythingLLM 实机闭环还没跑通**。

最近一轮 AI agent 改了什么：见 [`docs/CHANGELOG_DEV.md`](CHANGELOG_DEV.md)。本轮主要解决了你 [`docs/question.md`](question.md) 里反馈的 4 个痛点（端口冲突、`.env` 加载、宿主机解析不到 `anythingllm` 主机名、配置文件分工不清）。

---

## 3. 今晚你要做什么（共 3 步）

### 第 0 步：拉最新代码

```bash
cd /path/to/knowledge-base
git pull
git log --oneline -5    # 应能看到最近的提交
```

### 第 1 步：起服务、拉模型

```bash
# 端口默认 8081（80 常被占用），如果 8081 也被占就改 .env 里的 KB_WEB_PORT
docker compose up -d
docker ps                      # 应该看到 kb-ollama / kb-anythingllm / kb-worker / kb-web

# 拉模型（首次跑必须）
docker exec -it kb-ollama ollama pull qwen2.5:7b
docker exec -it kb-ollama ollama pull bge-m3
# 机器内存吃紧时可以改成 1.5b：编辑 .env 设 OLLAMA_MODEL=qwen2.5:1.5b 后 docker compose restart
```

访问：

```text
AnythingLLM    http://<服务器IP>:8301
kb-web         http://<服务器IP>:8081
```

进入 AnythingLLM 后台 → API Keys → 创建一个 Key → 写进项目根目录 `.env` 的 `ANYTHINGLLM_API_KEY=...`。

```bash
docker compose restart kb-worker kb-web   # 改完 .env 必须 restart 容器才能读到新值
```

### 第 2 步：跑诊断 + 导入 + 同步

**所有 CLI 命令都在 `kb-worker` 容器里执行**，不要在宿主机上跑（宿主机解析不到 `anythingllm` 这个主机名）。

```bash
docker exec -it kb-worker python -m kb.cli doctor
```

期望全部 ✅。如果某项 ❌，把整段输出保留下来。

```bash
# 导入用户
docker exec -it kb-worker python -m kb.cli import-users users.csv

# 准备一个测试文档
docker exec -it kb-worker bash -c '
  mkdir -p input/files/2026/05/12 &&
  echo "这是关于安全生产的通知正文。" > input/files/2026/05/12/7acf3850-4b7a-11f1-8da1-fa163e4c1d80.txt &&
  cat > input/file_meta.csv <<EOF
文件标识,文件标题,文件类型,文件名,文件事项ID,文件字号,文件流水号
7acf3850-4b7a-11f1-8da1-fa163e4c1d80,关于安全生产的通知,行政,7acf3850-4b7a-11f1-8da1-fa163e4c1d80.txt,sDKC3sDU,通知（10）号,20260512
EOF
  cat > input/sign.csv <<EOF
事项id,签阅人,签阅时间,签阅意见
sDKC3sDU,张三,2026/5/12 7:11,已阅
sDKC3sDU,李四,2026/5/12 11:11,同意
EOF
'

# 公共区导入
docker exec -it kb-worker python -m kb.cli import-docs \
  --zone public \
  --source ./input/files \
  --metadata ./input/file_meta.csv \
  --sign-records ./input/sign.csv

# 再跑一次，应输出"未变化跳过 1 个"——验证增量逻辑
docker exec -it kb-worker python -m kb.cli import-docs \
  --zone public --source ./input/files \
  --metadata ./input/file_meta.csv --sign-records ./input/sign.csv

# 给 wiki Markdown 写入完整 kb-web 跳转链接
docker exec -it kb-worker python -m kb.cli build-site --enrich-links

# 同步到 AnythingLLM（关键步骤）
docker exec -it kb-worker python -m kb.cli sync-anythingllm
```

### 第 3 步：人工验证 + 回传

打开 `http://<服务器IP>:8301`：

1. 是否多出三个 workspace（信息技术部 / 办公室 / 研究室）？workspace 名形如 `dept-xxxxxxxx`。
2. 任选一个 workspace，是否包含"关于安全生产的通知"？
3. 在 workspace 中提问：**"关于安全生产的通知谁签阅了？"** → 期望回答里包含 张三 / 李四 / 已阅 / 同意。
4. 用 admin 用户登录 `http://<服务器IP>:8081`（密码 admin123）→ 能否看到文档列表，能否点开详情，能否点"下载原文件"。

---

## 4. 把这些信息回传

不管成功还是失败，请回传以下内容（贴到聊天里给下一个 agent，agent 会接着改代码）：

```bash
# 容器状态
docker ps

# doctor 全部输出
docker exec kb-worker python -m kb.cli doctor

# 同步输出（含候选地址日志，不要截断）
docker exec kb-worker python -m kb.cli sync-anythingllm

# AnythingLLM 真实 API 路径（最关键）
打开浏览器 http://<服务器IP>:8301/api/docs
截图或复制如下接口的完整路径：
  - 创建 workspace
  - 创建 user
  - 给 workspace 分配 user
  - 上传 document
  - update embeddings

# 用户上传文件后的目录长什么样
docker exec kb-worker bash -c "find data/anythingllm -maxdepth 5 -type f | head -50"

# 任何一步报错的完整 stderr
```

有了这些信息，下一个 agent 就能精准修 `kb/anythingllm.py` 里的接口路径，不用瞎猜。

---

## 5. 我可能想看的别的文档

| 想知道什么 | 看哪个文件 |
|---|---|
| 项目要解决什么需求 | `doc/需求.md` + `docs/DESIGN.md` |
| `.env` 和 `config/config.yaml` 是啥关系 | `docs/CONFIG.md` |
| 当前完成度 / 还差什么 | `docs/PROGRESS.md` |
| 后面还要做什么功能 | `docs/NEXT_STEPS.md` |
| 上一轮 AI 改了什么 | `docs/CHANGELOG_DEV.md` |
| 操作手册（详细版） | `docs/HANDOFF_STEPS.md`（很长，本文是它的精简版） |
| 命令行能干啥 | `docs/OPERATIONS.md` |

---

## 6. 卡住怎么办

- **先看错误信息最末几行**，本轮 agent 已在 `kb/anythingllm.py` 的报错里加了"宿主机/容器"提示，照着做。
- **改完 `.env` 必须 `docker compose restart kb-worker kb-web`**，这是第二常见的"明明配了还说没配"的原因。
- **不要在宿主机直接跑 `python -m kb.cli sync-anythingllm`**，会报 `Failed to resolve 'anythingllm'`。所有 CLI 都在 `kb-worker` 容器里跑。
- 真要在宿主机跑：传 `--anythingllm-base-url http://localhost:8301`。
- 一次只动一个变量，否则不知道是哪里变好的或变坏的。
