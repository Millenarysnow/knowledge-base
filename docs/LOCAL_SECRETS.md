# 本地测试敏感配置备份

> 说明：本文件仅用于当前开发测试，最终交付前可以删除。  
> 由于 `.env` 现在被 `.gitignore` 忽略，仓库 clone 后不会自动带上本地 API Key。  
> 如果测试环境丢失 `.env`，可以按下面内容恢复。

## 1. AnythingLLM API Key

当前测试用 API Key：

```text
3WQYGVA-90P46DK-N453FQJ-RMKWSR4
```

需要放回的位置：项目根目录 `.env` 文件。

完整 `.env` 示例：

```bash
OLLAMA_MODEL=qwen2.5:7b
EMBEDDING_MODEL=bge-m3
ANYTHINGLLM_API_KEY=3WQYGVA-90P46DK-N453FQJ-RMKWSR4
```

## 2. docker-compose 使用方式

`docker-compose.yml` 会自动读取项目根目录 `.env`。

启动：

```bash
docker compose up -d
```

## 3. Python CLI 使用方式

Linux/macOS：

```bash
export ANYTHINGLLM_API_KEY=3WQYGVA-90P46DK-N453FQJ-RMKWSR4
python -m kb.cli sync-anythingllm
```

Windows CMD：

```cmd
set ANYTHINGLLM_API_KEY=3WQYGVA-90P46DK-N453FQJ-RMKWSR4
python -m kb.cli sync-anythingllm
```

如果是通过 docker compose 里的 `kb-worker` 执行，则 `.env` 会被 compose 自动注入容器。
