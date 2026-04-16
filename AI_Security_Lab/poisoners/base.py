"""Poisoner 平台层基类：在 environment_poisoning 攻击中于 PyRIT 触发请求前准备环境。"""

from __future__ import annotations

from typing import Any


class BasePoisoner:
    def prepare(self, agent_spec: dict, attack_case: dict) -> dict:
        raise NotImplementedError

    def cleanup(self, agent_spec: dict, attack_case: dict, context: dict) -> None:
        raise NotImplementedError
