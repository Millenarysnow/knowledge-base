#!/usr/bin/env python3
"""
智能知识库 - AI 分类器
调用 Ollama API 对文档进行 AI 分类、摘要生成、实体提取、[[wikilinks]] 关联发现
输入: raw/*.md（doc-parser.py 的输出）
输出: wiki/*.md（符合 LLM Wiki 规范的结构化 Markdown）

用法:
    python3 ai-classify.py [--input /app/storage/raw] [--output /app/storage/wiki]
"""
import os, sys, json, re, argparse, requests
from pathlib import Path
from datetime import datetime

# --- 配置 ---
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "300"))
CONFIG_FILE = "/app/config/config.yaml"

# --- 加载分类字典 ---
def load_categories():
    """从 config.yaml 加载分类定义"""
    cats = {}
    try:
        import yaml
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        clist = cfg.get("classification", {}).get("categories", [])
        for c in clist:
            cats[c["dir"]] = c
    except Exception:
        pass
    if not cats:
        cats = {
            "行政": {"dir": "行政", "label": "行政制度",
                     "keywords": ["制度","管理办法","规定","流程","规范","通知","公告","行政","考勤","薪酬","人事","财务","审计","合同"]},
            "技术": {"dir": "技术", "label": "技术文档",
                     "keywords": ["架构","接口","API","代码","部署","数据库","配置","服务","系统","开发","SDK","算法","网络","安全"]},
            "会议": {"dir": "会议", "label": "会议纪要",
                     "keywords": ["会议","纪要","讨论","决议","复盘","例会","评审","座谈","研讨"]},
            "报告": {"dir": "报告", "label": "工作报告",
                     "keywords": ["报告","分析","总结","调研","统计","年度","季度","月度","汇报","评估"]},
        }
    return cats


# --- 调用 Ollama ---
def ollama_chat(prompt, system="", timeout=TIMEOUT):
    """调用 Ollama /api/chat，返回文本"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": messages, "stream": False,
                  "options": {"temperature": 0.1, "num_predict": 1024}},
            timeout=timeout
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Ollama 调用失败: {e}")


# --- 备用 Ollama 检测 ---
def ollama_available():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


# --- 关键词兜底 ---
def keyword_fallback(text, categories):
    """Ollama 不可用时使用关键词匹配"""
    text_lower = text.lower()
    scores = {}
    for cat_key, cat in categories.items():
        score = 0
        for kw in cat.get("keywords", []):
            if kw.lower() in text_lower:
                score += 1
        scores[cat_key] = score
    max_score = max(scores.values()) if scores else 0
    if max_score == 0:
        return {"category": "未分类", "confidence": 0.0, "reason": "无匹配关键词"}
    best = max(scores, key=scores.get)
    return {"category": categories[best]["label"], "confidence": 0.3,
            "reason": f"关键词匹配({best})"}


# --- 步骤1: 分类判定 ---
def classify_document(text, title, categories):
    cat_list = "\n".join([
        f"{c['dir']}. {c['label']}（关键词: {', '.join(c.get('keywords', [])[:5])}）"
        for c in categories.values()
    ])

    prompt = f"""请判断以下文档最属于哪个分类，返回严格JSON。

可选分类：
{cat_list}
5. 未分类（不属于以上任何分类）

返回JSON格式：{{"category":"分类名","confidence":0.85,"reason":"判断理由(20字内)"}}

文档标题：{title}
文档内容（前2000字）：
{text[:2000]}"""

    try:
        result = ollama_chat(prompt, "你是文档分类助手，只返回JSON，不输出其他内容。")
        m = re.search(r'\{[^}]+\}', result)
        if m:
            data = json.loads(m.group())
            return data
    except Exception:
        pass

    return keyword_fallback(text, categories)


# --- 步骤2: 摘要生成 ---
def generate_summary(text):
    try:
        result = ollama_chat(
            f"请为以下文档生成200字以内的摘要：\n\n{text[:3000]}",
            "你是文档摘要助手，只返回摘要内容，不输出其他说明。",
            timeout=180
        )
        return result.strip()
    except Exception:
        return text[:200].strip() + "…"


# --- 步骤3: 实体提取 ---
def extract_entities(text):
    try:
        result = ollama_chat(
            f"""提取以下文档中的人名、部门名、项目名、日期、专业术语。
只返回JSON数组，如：["实体1","实体2"]

文档内容：
{text[:3000]}""",
            "你是信息抽取助手，只返回JSON数组，不输出其他内容。",
            timeout=180
        )
        m = re.search(r'\[.*?\]', result, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return []


# --- 步骤4: [[wikilinks]] 关联发现 ---
def discover_wikilinks(text, title, existing_titles):
    if not existing_titles:
        return []
    titles_str = "\n".join(f"- {t}" for t in existing_titles[:50])
    try:
        result = ollama_chat(
            f"""当前文档标题：「{title}」
知识库已有条目：
{titles_str}

请列出当前文档与哪些已有条目存在关联（引用、主题相关、同一项目等）。
只返回 [[条目名]] 格式，一行一个，最多5个。

文档内容（前2000字）：
{text[:2000]}""",
            timeout=180
        )
        links = re.findall(r'\[\[(.+?)\]\]', result)
        return list(set(links))[:5]
    except Exception:
        return []


# --- 解析 frontmatter ---
def parse_frontmatter(content):
    body = content
    fm = {}
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if m:
        body = content[m.end():]
        for line in m.group(1).split("\n"):
            if ":" in line:
                key, _, val = line.partition(":")
                fm[key.strip()] = val.strip()
    title = fm.get("title", "")
    src_category = fm.get("category", "")
    return title, src_category, body


# --- 主处理 ---
def process_one(raw_path, output_dir, categories, existing_titles):
    with open(raw_path, "r", encoding="utf-8") as f:
        content = f.read()

    title, src_category, body = parse_frontmatter(content)
    if not title:
        title = os.path.splitext(os.path.basename(raw_path))[0]

    print(f"  处理: {title} ...", end=" ")

    # 步骤1: AI分类
    cls = classify_document(body, title, categories)
    final_cat = cls["category"] if cls.get("confidence", 0) >= 0.6 else (src_category or "未分类")
    # 映射 label 到 dir（如 "行政制度" → "行政"）
    for cat_key, cat in categories.items():
        if cat["label"] == final_cat:
            final_cat = cat["dir"]
            break
    print(f"[{final_cat}]", end=" ")

    # 步骤2: 摘要
    summary = generate_summary(body)
    print(".", end="", flush=True)

    # 步骤3: 实体
    entities = extract_entities(body)
    print(".", end="", flush=True)

    # 步骤4: 关联
    wikilinks = discover_wikilinks(body, title, existing_titles)
    print(".")

    # 写入
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', title)
    output_path = os.path.join(output_dir, final_cat, f"{safe_name}.md")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    ts = datetime.now().isoformat()
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"""---
title: {title}
category: {final_cat}
auto_classified: true
confidence: {cls.get("confidence", 0)}
reason: {cls.get("reason", "")}
entities: {json.dumps(entities, ensure_ascii=False)}
summary: {summary}
wikilinks: {json.dumps(wikilinks, ensure_ascii=False)}
source_category: {src_category}
processed_at: {ts}
---

# {title}

## 摘要
{summary}

## 正文
{body}

## 关键实体
{chr(10).join(f'- **{e}**' for e in entities) if entities else '（未提取到实体）'}

## 相关文档
{chr(10).join(f'- [[{w}]]' for w in wikilinks) if wikilinks else '（未发现关联文档）'}
""")

    return title, final_cat


def collect_existing_titles(base_dir):
    titles = []
    if os.path.isdir(base_dir):
        for root, dirs, files in os.walk(base_dir):
            for fn in files:
                if fn.endswith(".md"):
                    titles.append(os.path.splitext(fn)[0])
    return titles


def main():
    ap = argparse.ArgumentParser(description="智能知识库 AI 分类器")
    ap.add_argument("--input", default="/app/storage/raw")
    ap.add_argument("--output", default="/app/storage/wiki")
    ap.add_argument("--force", action="store_true", help="强制重新处理所有文件（忽略缓存）")
    args = ap.parse_args()

    categories = load_categories()
    print(f"加载 {len(categories)} 个分类: {[c['label'] for c in categories.values()]}")

    use_ollama = ollama_available()
    if use_ollama:
        print(f"Ollama 可用: {OLLAMA_URL} (模型: {OLLAMA_MODEL})")
    else:
        print("Ollama 不可用，使用关键词兜底分类")

    existing = collect_existing_titles(args.output)

    success = 0
    fail = 0
    skipped = 0

    for root, dirs, files in os.walk(args.input):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            raw_path = os.path.join(root, fn)
            try:
                title, cat = process_one(raw_path, args.output, categories, existing)
                success += 1
                existing.append(title)
            except Exception as e:
                print(f"  [ERROR] {fn}: {e}")
                fail += 1

    print(f"\n分类完成: {success} 成功, {fail} 失败")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
