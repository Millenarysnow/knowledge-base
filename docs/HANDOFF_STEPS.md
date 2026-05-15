# 交接执行手册：今晚验证与下一步操作

> 交接对象：接下来在 Linux / Docker 环境中继续验证和开发的人。
> 当前分支：`feature/Claude优化`
> 当前最新提交：`1218bf4 增强同步能力与AI分类兜底`
> 目标：把当前已经开发好的本地知识库 MVP 在真实 Docker + AnythingLLM 环境中跑起来，并验证关键闭环。

---

## 0. 你需要先知道当前项目做到哪了

当前项目不是旧版 README 里的“llmwiki 脚本拼接项目”了，已经重构为：

```text
Ollama
  本地大模型和 embedding

AnythingLLM
  用户认证、用户上传、部门 workspace、RAG 问答

kbctl / KB Worker
  批量导入、元数据绑定、签阅记录绑定、文档解析、结构化 Markdown、同步 AnythingLLM

kb-web
  权限浏览、文档详情、原文件下载
```

当前已经实现：

- 部门/用户本地导入。
- 文件 + 元数据表 + 签阅记录表一批导入。
- 文件事项ID 与签阅记录关联。
- 签阅记录进入结构化 Markdown。
- 公共区/部门区目录组织。
- 元数据表分类 > 目录分类 > 文件名/内容关键词分类 > AI 分类 > 未分类。
- Ollama AI 分类兜底。
- AnythingLLM 同步代码骨架。
- kb-web 权限浏览服务。
- AnythingLLM 用户上传文件反向同步兜底。
- 冒烟测试。

当前还没完成实机验证：

- AnythingLLM API 实际接口是否完全匹配。
- 用户是否能真实创建并分配 workspace。
- 文档是否能真实上传并进入 workspace embedding。
- kb-web 是否能用真实 AnythingLLM 账号登录。
- AnythingLLM GUI 上传后的文件实际存储结构。

---

## 1. 拉取最新代码

进入项目目录：

```bash
cd /path/to/knowledge-base
```

切到当前分支：

```bash
git checkout feature/Claude优化
```

拉取最新：

```bash
git pull origin feature/Claude优化
```

确认最新提交：

```bash
git log --oneline -5
```

你应该能看到类似：

```text
1218bf4 增强同步能力与AI分类兜底
88e9fc1 增加权限浏览服务
95923b9 恢复环境配置并保留nginx正确挂载
...
```

---

## 2. 检查 `.env`

项目现在保留了 `.env`，里面有当前测试 API Key。

查看：

```bash
cat .env
```

应该类似：

```bash
OLLAMA_MODEL=qwen2.5:7b
EMBEDDING_MODEL=bge-m3
ANYTHINGLLM_API_KEY=3WQYGVA-90P46DK-N453FQJ-RMKWSR4
KB_WEB_PORT=8081
KB_WEB_PUBLIC_URL=http://localhost:8081
KB_WEB_ALLOW_LOCAL_AUTH=1
```

如果 `.env` 丢失，可以从：

```text
docs/LOCAL_SECRETS.md
```

复制回来。

> **重要**：修改 `.env` 后，必须执行 `docker compose restart kb-worker kb-web` 让容器读取新值。否则容器中的环境变量仍是旧的，会出现"`.env` 里明明配了 API_KEY，但执行命令报未设置"的诡异现象。

> 注意：当前为了方便开发测试，API Key 被保留在仓库里。最终交付前可以删除 `docs/LOCAL_SECRETS.md` 并清理 `.env`。

---

## 3. 启动 Docker 服务

在项目根目录执行：

```bash
docker compose up -d
```

查看容器：

```bash
docker ps
```

预期看到：

```text
kb-ollama
kb-anythingllm
kb-worker
kb-web
```

现在 `:8081` 是 `kb-web`，不是 Nginx。

访问地址：

```text
AnythingLLM: http://localhost:8301
权限浏览站点: http://localhost:8081
Ollama: http://localhost:11434
```

如果 `8081` 也被占用，可以改 `.env`：

```bash
KB_WEB_PORT=8082
```

然后 `docker compose up -d` 让端口生效。

---

## 4. 如果模型没下载，先拉模型

进入 Ollama 容器：

```bash
docker exec -it kb-ollama ollama list
```

如果没有模型，执行：

```bash
docker exec -it kb-ollama ollama pull qwen2.5:7b
```

嵌入模型：

```bash
docker exec -it kb-ollama ollama pull bge-m3
```

如果机器性能较差，可以改 `.env`：

```bash
OLLAMA_MODEL=qwen2.5:1.5b
```

然后重启服务：

```bash
docker compose restart
```

---

## 5. 初始化本地知识库

可以在宿主机运行，也可以进入 `kb-worker` 容器运行。

### 方式 A：宿主机运行

如果宿主机有 Python：

```bash
pip install -r requirements.txt
python -m kb.cli init
python -m kb.cli status
```

### 方式 B：容器里运行

```bash
docker exec -it kb-worker bash
python -m kb.cli init
python -m kb.cli status
```

预期看到：

```text
部门数: 3
- 信息技术部
- 办公室
- 研究室
```

也可以运行诊断命令，快速检查配置、数据库、Ollama 和 AnythingLLM 连通性：

```bash
python -m kb.cli doctor
```

如果是在容器里：

```bash
docker exec -it kb-worker python -m kb.cli doctor
```

---

## 6. 导入用户

项目根目录已有示例：

```text
users.csv
```

执行：

```bash
python -m kb.cli import-users users.csv
```

如果在容器里：

```bash
docker exec -it kb-worker python -m kb.cli import-users users.csv
```

然后查看：

```bash
python -m kb.cli status
```

---

## 7. 准备测试文档和表格

建议先用最小数据测试，不要一上来导大批真实文件。

创建目录：

```bash
mkdir -p input/files/2026/05/12
```

放一个测试文本文件：

```bash
echo "这是关于安全生产的通知正文。" > input/files/2026/05/12/7acf3850-4b7a-11f1-8da1-fa163e4c1d80.txt
```

创建文件元数据表：

```bash
cat > input/file_meta.csv <<'EOF'
文件标识,文件标题,文件类型,文件名,文件事项ID,文件字号,文件流水号
7acf3850-4b7a-11f1-8da1-fa163e4c1d80,关于安全生产的通知,行政,7acf3850-4b7a-11f1-8da1-fa163e4c1d80.txt,sDKC3sDU,通知（10）号,20260512
EOF
```

创建签阅记录表：

```bash
cat > input/sign.csv <<'EOF'
事项id,签阅人,签阅时间,签阅意见
sDKC3sDU,张三,2026/5/12 7:11,已阅
sDKC3sDU,李四,2026/5/12 11:11,同意
EOF
```

---

## 8. 导入公共区测试文档

执行：

```bash
python -m kb.cli import-docs \
  --zone public \
  --source ./input/files \
  --metadata ./input/file_meta.csv \
  --sign-records ./input/sign.csv
```

预期输出：

```text
文档导入完成: 成功 1 个, 失败 0 个
```

检查生成文件：

```bash
find data/wiki -type f
```

应该能看到：

```text
data/wiki/public/2026/05/12/行政/关于安全生产的通知.md
```

打开它，应该包含：

```text
张三
李四
通知（10）号
```

---

## 9. 构建浏览站点

虽然现在 `kb-web` 是动态服务，但仍可以生成静态站点用于检查导入结果：

```bash
python -m kb.cli build-site
```

---

## 10. 验证 kb-web 权限浏览

打开：

```text
http://localhost:8081
```

应该跳转到登录页。

当前 `.env` 中有：

```bash
KB_WEB_ALLOW_LOCAL_AUTH=1
```

所以即使 AnythingLLM 登录接口暂时失败，也可以用本地 users 表的账号密码登录。

当前 `users.csv` 里默认有 admin，密码一般是：

```text
admin / admin123
```

登录后检查：

- 是否能看到文档列表。
- 是否能看到“关于安全生产的通知”。
- 是否能进入文档详情页。
- 是否能下载原文件。

如果打不开，查看容器日志：

```bash
docker logs kb-web --tail 100
```

---

## 11. 创建或确认 AnythingLLM API Key

打开：

```text
http://localhost:8301
```

进入 AnythingLLM 后台，确认 API Key 是否可用。

当前 `.env` 中已有：

```bash
ANYTHINGLLM_API_KEY=3WQYGVA-90P46DK-N453FQJ-RMKWSR4
```

如果失效，就在 AnythingLLM 后台重新生成，然后更新 `.env`：

```bash
ANYTHINGLLM_API_KEY=新的key
```

重启 worker/web：

```bash
docker compose restart kb-worker kb-web
```

---

## 12. 同步到 AnythingLLM

先尝试完整同步：

```bash
python -m kb.cli sync-anythingllm
```

如果报用户相关错误，先跳过用户，只测 workspace 和文档：

```bash
python -m kb.cli sync-anythingllm --skip-users
```

如果希望强制全量同步：

```bash
python -m kb.cli sync-anythingllm --full
```

---

## 13. 检查 AnythingLLM 同步结果

打开：

```text
http://localhost:8301
```

检查：

1. 是否有三个部门对应 workspace：
   - 信息技术部
   - 办公室
   - 研究室
2. 公共文档是否进入所有部门 workspace。
3. 如果导入部门文档，是否只进入对应部门 workspace。
4. 用户是否能登录。
5. 用户是否只看到自己部门 workspace。

---

## 14. 验证问答是否命中签阅记录

在 AnythingLLM 中对相应 workspace 提问：

```text
关于安全生产的通知谁签阅了？
```

期望回答包含：

```text
张三 2026/5/12 7:11 已阅
李四 2026/5/12 11:11 同意
```

如果回答不到，优先检查：

1. `data/wiki/.../关于安全生产的通知.md` 是否包含签阅记录。
2. 该 markdown 是否上传到 AnythingLLM。
3. 是否执行了 `update-embeddings`。
4. AnythingLLM workspace 中是否能看到该文档。

---

## 15. 验证用户通过 AnythingLLM 上传文件

需求要求：用户上传文件只能通过 AnythingLLM 界面。

测试步骤：

1. 登录普通用户。
2. 进入本部门 workspace。
3. 使用 AnythingLLM 界面上传一个文件。
4. 记录上传后文件能否在 AnythingLLM 中问答。
5. 查看本地存储目录结构：

```bash
find data/anythingllm -maxdepth 5 -type f | head -100
```

把目录结构记录下来。

---

## 16. 从 AnythingLLM 反向同步用户上传文件

当前已提供兜底命令：

```bash
python -m kb.cli sync-from-anythingllm
```

如果路径中无法识别部门，可以指定默认部门：

```bash
python -m kb.cli sync-from-anythingllm --default-dept 信息技术部
```

执行后检查：

```bash
find data/documents -type f
find data/wiki -type f
```

如果能看到用户上传的文件，说明兜底同步可用。

如果不能，需要根据第 15 步观察到的 `data/anythingllm` 实际目录结构修改：

```text
kb/sync_from_anythingllm.py
```

---

## 17. 常见问题与处理

### 17.1 docker compose 启动失败

查看日志：

```bash
docker compose logs --tail 100
```

单独看服务：

```bash
docker logs kb-anythingllm --tail 100
docker logs kb-worker --tail 100
docker logs kb-web --tail 100
```

### 17.2 80 端口被占用

修改 `docker-compose.yml`：

```yaml
ports:
  - "8080:8000"
```

然后访问：

```text
http://localhost:8080
```

### 17.3 AnythingLLM API 同步失败

打开：

```text
http://localhost:8301/api/docs
```

核对接口。

重点修：

```text
kb/anythingllm.py
```

常见可能不一致：

- workspace 创建接口。
- 用户创建接口。
- workspace 用户分配接口。
- 文档上传接口。
- update embeddings 接口。

### 17.4 kb-web 登录失败

如果 AnythingLLM 登录失败，先确认 `.env`：

```bash
KB_WEB_ALLOW_LOCAL_AUTH=1
```

然后用本地 users 表账号密码登录。

例如：

```text
admin / admin123
```

如果仍失败，检查是否导入用户：

```bash
python -m kb.cli import-users users.csv
```

### 17.5 问答搜不到签阅记录

检查 markdown：

```bash
grep -R "张三" data/wiki
```

如果 markdown 有签阅记录，但 AnythingLLM 问不到，说明同步/embedding 有问题。

重新同步：

```bash
python -m kb.cli sync-anythingllm --full
```

### 17.6 AI 分类没有生效

AI 分类只在前三种分类失败时触发：

```text
元数据表分类
目录分类
文件名/内容关键词分类
```

如果这三者已经命中，就不会调用 AI。

如果要测试 AI 分类，可以导入一个没有分类、目录也不含分类关键词的文件。

还要确认 Ollama 可用：

```bash
curl http://localhost:11434/api/tags
```

---

## 18. 验证结果要反馈什么

请把下面信息反馈给后续开发者/Agent：

### 18.1 Docker 状态

```bash
docker ps
```

### 18.2 AnythingLLM API 文档截图或接口信息

打开：

```text
http://localhost:8301/api/docs
```

重点反馈：

- 创建 workspace 的接口。
- 创建用户的接口。
- 分配用户 workspace 的接口。
- 上传文件的接口。
- update embeddings 的接口。

### 18.3 sync-anythingllm 输出

把完整输出贴出来：

```bash
python -m kb.cli sync-anythingllm
```

### 18.4 kb-web 登录结果

说明：

- AnythingLLM 登录是否成功。
- 本地兜底登录是否成功。
- 普通用户权限是否正确。
- 管理员权限是否正确。

### 18.5 用户上传文件目录结构

执行：

```bash
find data/anythingllm -maxdepth 5 -type f | head -100
```

把结果贴出来。

---

## 19. 当前未完成事项清单

当前还没有彻底完成：

1. AnythingLLM API 实机适配。
2. AnythingLLM workspace 问答隔离实测。
3. AnythingLLM 用户上传文件的精确同步。
4. AnythingLLM 回答中的来源链接跳转到 kb-web 文档页。
5. 扫描 PDF OCR。
6. 高级知识图谱可视化。
7. 签阅记录重复导入去重。
8. 更完善的 doctor 诊断命令。

---

## 20. 最短验证路径

如果时间有限，只做这几步：

```bash
docker compose up -d
python -m kb.cli init
python -m kb.cli import-users users.csv
python -m kb.cli import-docs --zone public --source ./input/files --metadata ./input/file_meta.csv --sign-records ./input/sign.csv
python -m kb.cli sync-anythingllm --skip-users
```

然后验证：

```text
http://localhost:8301  能否问到文档和签阅记录
http://localhost:8081  能否登录并浏览文档
```

这就是当前 MVP 的最小闭环。
