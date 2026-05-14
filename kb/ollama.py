from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


def ollama_chat(
    base_url: str,
    model: str,
    prompt: str,
    system: str = "",
    timeout: int = 180,
    temperature: float = 0.1,
) -> str:
    if requests is None:
        raise RuntimeError("缺少 requests 依赖")
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    r = requests.post(
        base_url.rstrip("/") + "/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 512},
        },
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("message", {}).get("content", "")


def ollama_available(base_url: str, timeout: int = 5) -> bool:
    if requests is None:
        return False
    try:
        r = requests.get(base_url.rstrip("/") + "/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False
