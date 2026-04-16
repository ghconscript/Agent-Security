"""
根据 Agent 标签与 attack taxonomy 筛选适用的 attack family 与基准样本。
"""

from __future__ import annotations

from typing import Any

from agent_registry import AgentSpec, get_agent_tags


def _normalize_tags(tags: list[str]) -> set[str]:
    return {t.strip().lower() for t in tags if t and str(t).strip()}


def _family_applies_to_agent(family: dict[str, Any], agent_tag_set: set[str]) -> bool:
    excludes = family.get("excludes") or []
    for x in excludes:
        if str(x).strip().lower() in agent_tag_set:
            return False

    applies_to_all = family.get("applies_to_all") or []
    if applies_to_all:
        needed = {str(x).strip().lower() for x in applies_to_all}
        if not needed.issubset(agent_tag_set):
            return False

    applies_to_any = family.get("applies_to_any") or []
    if applies_to_any:
        any_set = {str(x).strip().lower() for x in applies_to_any}
        if agent_tag_set.isdisjoint(any_set):
            return False

    return True


def select_attack_families(agent_tags: list[str], taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    """返回该 Agent 适用的 attack family 定义列表（taxonomy 中的完整 dict）。"""
    tag_set = _normalize_tags(agent_tags)
    out: list[dict[str, Any]] = []
    for fam in taxonomy.get("attack_families") or []:
        if not isinstance(fam, dict):
            continue
        fid = fam.get("id")
        if not fid:
            continue
        if _family_applies_to_agent(fam, tag_set):
            out.append(fam)
    return out


def select_attack_cases_for_agent(
    agent_spec: AgentSpec,
    attack_bench: list[dict[str, Any]],
    taxonomy: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    从全量 attack_bench 中筛出当前 Agent 可用的样本（按 family 与标签匹配）。
    """
    families = select_attack_families(get_agent_tags(agent_spec), taxonomy)
    allowed_ids = {str(f["id"]) for f in families if f.get("id")}
    return [row for row in attack_bench if str(row.get("family", "")) in allowed_ids]
