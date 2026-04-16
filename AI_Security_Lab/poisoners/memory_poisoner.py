"""长期记忆投毒占位。"""

from __future__ import annotations

from typing import Any

from poisoners.base import BasePoisoner


class MemoryPoisoner(BasePoisoner):
    def prepare(self, agent_spec: dict, attack_case: dict) -> dict:
        return {"memory_poison_stub": True, "note": "v1 stub: no real memory store"}

    def cleanup(self, agent_spec: dict, attack_case: dict, context: dict) -> None:
        return
