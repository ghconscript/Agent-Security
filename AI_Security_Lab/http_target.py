"""
HttpTarget：通过 HTTP 接口与 Agent 通信的 Target 实现。

约定常见 JSON 返回字段由 output_key 指定（默认 output）；兼容 reply。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import requests


@dataclass
class HttpTarget:
    base_url: str
    path: str = "/chat"
    method: str = "POST"
    input_key: str = "input"
    output_key: str = "output"
    timeout: float = 30.0
    identifier: str = ""
    health_path: str = "/"

    def run(self, *args: Any, **kwargs: Any) -> str:
        """执行请求；可 run(text) 或 run(**{input_key: text, ...})。"""
        if args:
            if len(args) != 1 or not isinstance(args[0], str):
                raise TypeError("HttpTarget.run expects at most one str positional message")
            if self.input_key in kwargs:
                raise TypeError("pass either positional message or input_key kw, not both")
            kwargs = {self.input_key: args[0], **kwargs}

        url = self.base_url.rstrip("/") + self.path
        if self.input_key in kwargs:
            payload: Dict[str, Any] = dict(kwargs)
        elif "message" in kwargs:
            payload = {self.input_key: kwargs["message"], **{k: v for k, v in kwargs.items() if k != "message"}}
        else:
            payload = dict(kwargs)
        if self.input_key not in payload and kwargs:
            first_str = next((v for v in kwargs.values() if isinstance(v, str)), None)
            if first_str is not None:
                payload = {self.input_key: first_str, **{k: v for k, v in kwargs.items()}}

        m = self.method.upper()
        if m == "POST":
            resp = requests.post(url, json=payload, timeout=self.timeout)
        elif m == "GET":
            resp = requests.get(url, params=payload, timeout=self.timeout)
        else:
            raise ValueError(f"Unsupported method: {self.method}")
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            if self.output_key in data:
                return str(data[self.output_key])
            if "output" in data:
                return str(data["output"])
            if "reply" in data:
                return str(data["reply"])
        return str(data)

    def healthcheck(self) -> bool:
        """
        GET base_url + health_path；失败时再尝试最小 POST /chat（若配置了）以免仅根路径不可达时误判。
        """
        base = self.base_url.rstrip("/")
        hp = (self.health_path or "/").strip() or "/"
        if not hp.startswith("/"):
            hp = "/" + hp
        try:
            r = requests.get(f"{base}{hp}", timeout=min(5.0, self.timeout))
            if 200 <= r.status_code < 500:
                return True
        except Exception:
            pass
        try:
            ping = {self.input_key: "__registry_ping__"}
            url = base + self.path
            if self.method.upper() == "POST":
                r2 = requests.post(url, json=ping, timeout=min(8.0, self.timeout))
            else:
                r2 = requests.get(url, params=ping, timeout=min(8.0, self.timeout))
            return 200 <= r2.status_code < 600
        except Exception:
            return False

    def describe(self) -> dict[str, Any]:
        return {
            "target_kind": "http",
            "identifier": self.identifier or self.base_url,
            "base_url": self.base_url,
            "path": self.path,
            "input_key": self.input_key,
            "run_param_name": self.input_key,
            "method": self.method,
            "output_key": self.output_key,
            "health_path": self.health_path,
        }
