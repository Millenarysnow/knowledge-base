# 智能知识库

本地化团队知识管理平台，AnythingLLM + LLM Wiki + Ollama，纯脚本零代码。

## 架构

```
                         访问入口
                            │
    ┌───────────┬───────────┼───────────┬───────────┐
    │           │           │           │           │
    ▼           ▼           ▼           ▼           ▼
 :80        :8301       :8888       命令行       crontab
 Nginx      AnythingLLM  部门上传   compile-wiki  定时更新
 浏览        问答         界面        import
                            │
    ┌───────────────────────┼───────────────────────┐
    │                       ▼                       │
    │  ┌──────────┐  ┌──────────────┐  ┌──────────┐ │
    │  │ Ollama   │  │ LLM Wiki     │  │ 自建脚本  │ │
    │  │ :11434   │  │ build        │  │ doc-parser│ │
    │  │ LLM推理   │  │ 编译+图谱     │  │ ai-classify│ │
    │  └──────────┘  └──────────────┘  └──────────┘ │
    └───────────────────────────────────────────────┘
```

## 文件结构

```
knowledge-base/

├── install.sh                   # 一键安装
├── docker-compose.yml           # 4 服务编排
├── .env                         # 环境变量
├── README.md
├── llmwiki/config.yaml          # 分类配置
├── nginx/conf.d/default.conf    # Nginx 配置
├── scripts/
│   ├── compile-wiki.sh          # ★ 主控脚本（日常唯一入口）
│   ├── doc-parser.py            # 文档解析: PDF/DOCX → raw/*.md
│   ├── ai-classify.py           # AI分类: 调用Ollama → wiki/*.md
│   ├── auto-sort.sh             # 自动归类
│   ├── upload-server.py         # 部门上传界面
│   ├── create-dept.sh           # 创建单个部门
│   ├── import-dept.sh           # 导入文档到部门
│   ├── import-users.sh          # CSV/Excel 批量导入部门+用户
│   ├── import-view-records.py   # 导入文件查阅记录
│   ├── manage-workspaces.sh     # AnythingLLM workspace管理
│   ├── pull-models.sh           # 模型拉取
│   └── update-kb.sh             # 定时增量更新
├── users.csv                    # 部门/用户模板
└── volumes/
    ├── ollama/
    ├── anythingllm/
    ├── documents/               # 数据源
    │   ├── public/              #   公共区
    │   │   └── YYYY/MM/DD/分类/文件
    │   └── dept-信息技术部/      #   部门区
    │       └── YYYY/MM/DD/分类/文件
    ├── llm-wiki-storage/
    │   ├── raw/                 # 文档解析产物
    │   └── wiki/                # AI 分类后结构化条目
    ├── llm-wiki-site/           # 静态站点
    └── users/                   # 部门/用户数据
```

## 快速开始

```bash
# 1. 一键安装
chmod +x install.sh scripts/*.sh
./install.sh

# 2. 批量导入文档
./scripts/compile-wiki.sh import /path/to/docs/

# 3. 导入到部门
./scripts/compile-wiki.sh import /path/to/docs/ --dept 信息技术部

# 4. 导入文件查阅记录（可选）
./scripts/compile-wiki.sh import-records ./查阅记录.csv

# 5. 访问
#    知识浏览:   http://localhost
#    智能问答:   http://localhost:8301
#    部门上传:   http://localhost:8888/upload
```

## 完整数据流

```
原始文档 (PDF/DOCX/WPS/OFD/MD/TXT)
    │
    ▼  doc-parser.py（自建）
    │  pypdf / python-docx / LibreOffice 兜底
storage/raw/<分类>/<文件名>.md       ← 纯文本 + frontmatter
    │
    ▼  ai-classify.py（自建，调用 Ollama）
    │  分类判定 + 摘要 + 实体提取 + [[wikilinks]]
storage/wiki/<分类>/<文件名>.md      ← 结构化 Markdown
    │
    ▼  llmwiki build（LLM Wiki 原生）
    │  HTML + search-index + graph.jsonld + llms.txt
site/                               ← 静态站点产物
    │
    ├─→ Nginx :80       ← 浏览 + 知识图谱
    └─→ AnythingLLM :8301 ← RAG 问答 + 溯源下载
```

## 命令清单

| 命令 | 用途 |
|------|------|
| `./scripts/compile-wiki.sh import <目录>` | 批量导入到公共区 |
| `./scripts/compile-wiki.sh import <目录> --dept <部门>` | 导入到部门区 |
| `./scripts/compile-wiki.sh import-records <csv>` | 导入文件查阅记录 |
| `./scripts/compile-wiki.sh build` | 重新编译站点 |
| `./scripts/compile-wiki.sh status` | 查看统计和状态 |
| `./scripts/import-users.sh users.csv` | 批量导入部门/用户 |
| `./scripts/create-dept.sh <部门名>` | 创建单个部门 |
| `./scripts/pull-models.sh` | 拉取/切换模型 |
| `./scripts/manage-workspaces.sh init` | 创建 AnythingLLM workspace |

## 部门隔离

| 用户 | 问答可见范围 |
|------|------------|
| 所有用户 | 公共区 |
| 信息技术部成员 | 公共区 + 信息技术部 |
| 办公室成员 | 公共区 + 办公室 |
| 研究室成员 | 公共区 + 研究室 |

## 模型切换

编辑 `.env`:
```bash
OLLAMA_MODEL=qwen2.5:1.5b   # 轻量（8GB内存）
OLLAMA_MODEL=qwen2.5:7b     # 标准（16GB内存）
OLLAMA_MODEL=qwen2.5:14b    # 性能（32GB内存）
```

## 自动更新

```bash
(crontab -l 2>/dev/null; echo "0 2 * * * $(pwd)/scripts/update-kb.sh") | crontab -
```

## 支持格式

PDF / DOCX / DOC / WPS / OFD / MD / TXT
