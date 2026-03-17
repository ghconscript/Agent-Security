"""
HttpTarget：通过 HTTP 接口与 Agent 通信的 Target 实现。

约定对方暴露一个 POST 接口，比如 /chat，接受 {"input": "..."}，返回 {"output": "..."}。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import requests


@dataclass
class HttpTarget:
    base_url: str
    path: str = "/chat"
    input_key: str = "input"
    timeout: float = 30.0

    def run(self, message: str, **kwargs: Any) -> str:
        payload: Dict[str, Any] = {self.input_key: message}
        payload.update(kwargs)
        url = self.base_url.rstrip("/") + self.path
        resp = requests.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        # 约定对方返回 {"output": "..."}，否则直接转字符串
        return str(data.get("output", data))

