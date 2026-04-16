"""
演示用 Poisoner：将 poison_payload 写入本地 artifacts 目录，模拟「提示词文件被篡改」。
不修改真实 Agent 进程；cleanup 删除文件。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from poisoners.base import BasePoisoner

ROOT = Path(__file__).resolve().parent.parent


class PromptFilePoisoner(BasePoisoner):
    def prepare(self, agent_spec: dict, attack_case: dict) -> dict:
        exp = attack_case.get("_experiment_id") or "default"
        aid = attack_case.get("attack_id") or "unknown"
        agent_id = agent_spec.get("id") or "agent"
        poison = attack_case.get("poison_payload") or ""
        base = ROOT / "artifacts" / "poison_demo" / str(exp) / agent_id
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{aid}_prompt_poison.txt"
        path.write_text(poison, encoding="utf-8")
        return {"poison_file": str(path.resolve())}

    def cleanup(self, agent_spec: dict, attack_case: dict, context: dict) -> None:
        p = context.get("poison_file")
        if not p:
            return
        path = Path(p)
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass
