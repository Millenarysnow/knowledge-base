# 配置说明：`.env` 与 `config/config.yaml` 的分工

很多新接手项目的人会困惑这两个文件的关系。简单结论：

| 文件 | 装什么 | 谁可以改 | 修改后 |
|---|---|---|---|
| `.env` | **部署差异 + 敏感凭据**：API Key、模型名、对外端口、kb-web 公开 URL、是否允许本地兜底登录 | 部署人员 | 改完必须 `docker compose restart` 让容器看到新值 |
| `config/config.yaml` | **业务字典 + 路径**：默认部门列表、分类字典/关键词、文档存储路径、AnythingLLM 默认地址 | 项目维护者 | 改完容器里的代码热加载即可（kb-worker / kb-web 重启更稳） |

## 1. `.env` 字段

```bash
# Ollama 推理用模型，低配机器可改 qwen2.5:1.5b
OLLAMA_MODEL=qwen2.5:7b

# Embedding 模型
EMBEDDING_MODEL=bge-m3

# AnythingLLM 后台创建的 API Key，sync-anythingllm 命令必需
ANYTHINGLLM_API_KEY=

# kb-web 对外端口（docker-compose 会读取）
KB_WEB_PORT=8081

# kb-web 对外完整 URL，被写进结构化 Markdown，让 AnythingLLM 引用可点击跳转
KB_WEB_PUBLIC_URL=http://localhost:8081

# 开发兜底：AnythingLLM 不可用时允许本地 users 表密码登录
KB_WEB_ALLOW_LOCAL_AUTH=1

# 可选：宿主机执行 CLI 时覆盖 AnythingLLM 地址
# 容器内执行（推荐）：留空，自动用 docker 网络的 anythingllm:3001
# 宿主机执行：设为 http://localhost:8301
ANYTHINGLLM_BASE_URL=
```

## 2. `config/config.yaml` 重点字段

```yaml
departments:        # init 默认创建的部门
  - 信息技术部
  - 办公室
  - 研究室

categories:         # 分类字典：分类优先级里"关键词分类"和"AI 分类"都依赖这里
  - key: 行政
    keywords: [...]

models:             # Ollama 默认地址（容器内）
  ollama_base_url: http://ollama:11434

anythingllm:        # AnythingLLM 默认地址（容器内）
  base_url: http://anythingllm:3001
  api_key_env: ANYTHINGLLM_API_KEY

site:
  public_url: http://localhost:8081  # 可被 KB_WEB_PUBLIC_URL 覆盖
```

## 3. 优先级

代码读取顺序统一为：

```text
环境变量（含 docker-compose 注入 + .env 加载）
    ↓ 没找到
config/config.yaml
    ↓ 没找到
代码内的硬编码默认值
```

`.env` 加载的细节：`kb/cli.py` 在 `main()` 入口先调用 `load_dotenv()`；`_load_env_file` 不会用 `.env` 的值覆盖**已存在且非空**的环境变量，但会覆盖 docker-compose `${VAR:-}` 注入的空字符串。

## 4. 常见踩坑

### 4.1 `.env` 改了但报"未设置 API_KEY"

容器是 docker-compose 启动时一次性注入环境变量的，启动后再改 `.env`，正在运行的容器不会自动更新。

```bash
# 改完 .env 后必须执行：
docker compose restart kb-worker kb-web
```

### 4.2 宿主机直接 `python -m kb.cli sync-anythingllm` 报 `Failed to resolve 'anythingllm'`

容器主机名 `anythingllm` 只能在 docker 网络里解析。在宿主机上要传：

```bash
python -m kb.cli --anythingllm-base-url http://localhost:8301 sync-anythingllm
# 或 .env 中设
ANYTHINGLLM_BASE_URL=http://localhost:8301
```

更推荐：直接进容器跑，避免环境差异。

```bash
docker exec -it kb-worker python -m kb.cli sync-anythingllm
```

### 4.3 端口 80 被占用，容器起不来

`.env` 加 `KB_WEB_PORT=8081` 然后 `docker compose up -d`。访问改成 `http://localhost:8081`。
