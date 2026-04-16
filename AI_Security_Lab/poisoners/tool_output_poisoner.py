"""工具输出投毒占位。"""

from __future__ import annotations

from typing import Any

from poisoners.base import BasePoisoner


class ToolOutputPoisoner(BasePoisoner):
    def prepare(self, agent_spec: dict, attack_case: dict) -> dict:
        return {"tool_poison_stub": True, "note": "v1 stub: no tool hook"}

    def cleanup(self, agent_spec: dict, attack_case: dict, context: dict) -> None:
        return
