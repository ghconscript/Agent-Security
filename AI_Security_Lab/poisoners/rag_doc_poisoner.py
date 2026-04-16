"""RAG 文档投毒：v1 演示 —将 poison_payload 写入模拟「向量库条目」JSONL，供后续接入真实 RAG。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from poisoners.base import BasePoisoner

ROOT = Path(__file__).resolve().parent.parent


class RagDocPoisoner(BasePoisoner):
    def prepare(self, agent_spec: dict, attack_case: dict) -> dict:
        exp = attack_case.get("_experiment_id") or "default"
        aid = attack_case.get("attack_id") or "unknown"
        agent_id = agent_spec.get("id") or "agent"
        doc = {
            "id": aid,
            "text": attack_case.get("poison_payload") or "",
            "source": "poisoners.rag_doc_poisoner",
        }
        base = ROOT / "artifacts" / "poison_demo" / str(exp) / agent_id
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{aid}_rag_doc.jsonl"
        path.write_text(json.dumps(doc, ensure_ascii=False) + "\n", encoding="utf-8")
        return {"rag_doc_file": str(path.resolve())}

    def cleanup(self, agent_spec: dict, attack_case: dict, context: dict) -> None:
        p = context.get("rag_doc_file")
        if not p:
            return
        path = Path(p)
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass
