from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


class AnythingLLMAuthError(RuntimeError):
    pass


class AnythingLLMAuth:
    """基于 AnythingLLM 的账号密码校验。

    该模块用于后续 KB Web 权限控制：
    - 用户输入 AnythingLLM 账号密码。
    - 调用 /api/request-token 校验。
    - 再结合本地 users 表判断用户部门/角色。

    当前 CLI MVP 暂未启用 Web 服务，但先保留认证封装。
    """

    def __init__(self, base_url: str):
        if requests is None:
            raise RuntimeError("缺少 requests 依赖")
        self.base_url = base_url.rstrip("/")

    def request_token(self, username: str, password: str) -> Dict[str, Any]:
        url = self.base_url + "/api/request-token"
        resp = requests.post(url, json={"username": username, "password": password}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("valid"):
            raise AnythingLLMAuthError(data.get("message") or "AnythingLLM 登录失败")
        return data

    def check_token(self, token: str) -> bool:
        url = self.base_url + "/api/system/check-token"
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if resp.status_code != 200:
            return False
        return bool(resp.json().get("valid"))
