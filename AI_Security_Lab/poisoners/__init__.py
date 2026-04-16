"""Poisoner 注册表。"""

from __future__ import annotations

from typing import Any

from poisoners.base import BasePoisoner
from poisoners.memory_poisoner import MemoryPoisoner
from poisoners.prompt_file_poisoner import PromptFilePoisoner
from poisoners.rag_doc_poisoner import RagDocPoisoner
from poisoners.tool_output_poisoner import ToolOutputPoisoner

_REGISTRY: dict[str, type[BasePoisoner]] = {
    "prompt_file_poisoner": PromptFilePoisoner,
    "rag_doc_poisoner": RagDocPoisoner,
    "memory_poisoner": MemoryPoisoner,
    "tool_output_poisoner": ToolOutputPoisoner,
}


def get_poisoner(poisoner_type: str | None) -> BasePoisoner | None:
    if not poisoner_type:
        return None
    cls = _REGISTRY.get(str(poisoner_type))
    if cls is None:
        return None
    return cls()
