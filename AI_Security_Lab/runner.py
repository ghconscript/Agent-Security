"""
v1 执行入口：HTTP registry + attack taxonomy + PyRIT + 规则 scorer + 结构化报告。
MetaAgent / inproc 不在此主链路。

PyRIT 在本项目中的角色（不是「只能发 HTTP」）：
- PromptSendingAttack：把「objective →（可选）converter → target → scorer」串成一次可记录的攻击步；
- 与手写 requests 循环相比：统一 Message/Score、可挂多种 PromptConverter、后续可换多轮编排器。
「投毒写入环境」仍由 poisoners/ 完成，不由 PyRIT 代劳。

与 DeepSeek 的分工：
- DeepSeek（llm_judge_deepseek）：事后语义判分 / 可选覆盖 final_label，属「评测层」；
- adaptive_planner：根据 run_summary 规则建议下一轮 family/换壳，属「策略层」，可 --invoke-runner 自动再跑一轮；
- 攻击族与标签：由 attack_taxonomy + attack_selector 定义，不在 adaptive 里重写。
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pyrit.executor.attack.core.attack_config import AttackConverterConfig, AttackScoringConfig
from pyrit.executor.attack.single_turn.prompt_sending import PromptSendingAttack
from pyrit.memory import CentralMemory, SQLiteMemory
from pyrit.prompt_converter import TextJailbreakConverter
from pyrit.datasets import TextJailBreak
from pyrit.prompt_normalizer import PromptConverterConfiguration

from agent_registry import (
    build_http_target_from_spec,
    get_agent_tags,
    is_benchmark_target,
    load_agents_registry,
    validate_agent_spec,
)
from attack_selector import select_attack_cases_for_agent
from poisoners import get_poisoner
from pyrit_adapter import PyRITAdapter
from llm_judge_deepseek import deepseek_judge_sync, is_llm_judge_enabled
from scorers import compute_structured_outcome, scorer_from_bench_row

ROOT = Path(__file__).resolve().parent
DEFAULT_AGENTS_YAML = ROOT / "configs" / "agents.yaml"
DEFAULT_BENCH = ROOT / "attack_bench.jsonl"
DEFAULT_TAXONOMY = ROOT / "configs" / "attack_taxonomy.yaml"
DEFAULT_AGENT_POOLS = ROOT / "configs" / "agent_pools.yaml"
ARTIFACTS = ROOT / "artifacts"
EXPERIMENTS_DIR = ARTIFACTS / "experiments"


def _load_dotenv() -> None:
    for _f in (ROOT / ".env", ROOT / ".env.example"):
        if _f.is_file():
            with open(_f, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k:
                            os.environ.setdefault(k, v)
            break


def load_attack_bench(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def load_taxonomy(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_agent_pools(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def resolve_experiment_agents(
    agents: list[Any],
    root: Path,
    pools_data: dict[str, Any],
    *,
    agent_ids: list[str] | None,
    pool_name: str | None,
    pool_rotate_index: int | None,
    pool_failover: str | None,
) -> tuple[list[Any], dict[str, Any]]:
    """
    按 agent_pools / --agent-ids 筛选本轮要跑的 agent。
    pool_failover：从池中按顺序找第一个 HTTP healthcheck 通过的，只返回该 1 个。
    pool + pool_rotate_index：只返回池中下标 K % len 的那一个。
    """
    meta: dict[str, Any] = {}
    id_map = {a.id: a for a in agents}
    pools = pools_data.get("pools") or {}

    if pool_failover:
        plist = pools.get(pool_failover) or []
        meta["pool_failover"] = pool_failover
        for aid in plist:
            if aid not in id_map:
                continue
            spec = id_map[aid]
            if validate_agent_spec(spec, root):
                continue
            rt = spec.runtime
            if not rt or rt.deployment != "local_http":
                continue
            try:
                ht = build_http_target_from_spec(spec)
                if ht.healthcheck():
                    meta["selected_agent_id"] = aid
                    meta["selection_mode"] = "pool_failover_first_healthy"
                    return [spec], meta
            except Exception:
                continue
        meta["selection_mode"] = "pool_failover"
        meta["error"] = "no_healthy_agent_in_pool"
        return [], meta

    if pool_name and pool_rotate_index is not None:
        plist = pools.get(pool_name) or []
        if not plist:
            meta["error"] = "empty_pool"
            return [], meta
        rid = plist[pool_rotate_index % len(plist)]
        meta["pool"] = pool_name
        meta["pool_rotate_index"] = pool_rotate_index
        meta["selected_agent_id"] = rid
        meta["selection_mode"] = "pool_rotate"
        if rid not in id_map:
            meta["error"] = "agent_not_in_registry"
            return [], meta
        return [id_map[rid]], meta

    pool_list = pools.get(pool_name) if pool_name else None

    if pool_list is not None:
        candidate_order = [x for x in pool_list if x in id_map]
        if agent_ids:
            af = {x.strip() for x in agent_ids if x.strip()}
            candidate_order = [x for x in candidate_order if x in af]
    elif agent_ids:
        candidate_order = [x.strip() for x in agent_ids if x.strip() and x.strip() in id_map]
    else:
        candidate_order = [a.id for a in agents]

    if not candidate_order:
        meta["error"] = "no_matching_agents"
        meta["selection_mode"] = "filter"
        return [], meta

    meta["selection_mode"] = "filter"
    meta["selected_agent_ids"] = candidate_order
    return [id_map[i] for i in candidate_order], meta


def _agent_spec_dict(spec: Any) -> dict[str, Any]:
    return spec.model_dump()


def _pyrit_result_reply(result: Any) -> str:
    if result and getattr(result, "last_response", None):
        return (
            getattr(result.last_response, "converted_value", None)
            or getattr(result.last_response, "original_value", None)
            or ""
        )[:4000]
    return ""


def _pyrit_scorer_bool(result: Any) -> bool | None:
    if result and result.last_score:
        v = result.last_score.get_value()
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
    return None


async def execute_attack_case(
    *,
    adapter: PyRITAdapter,
    objective: str,
    attack_family: str,
    objective_scorer: Any,
    use_jailbreak_converter: bool,
) -> Any:
    if use_jailbreak_converter:
        jailbreak = TextJailBreak(random_template=True)
        converter = TextJailbreakConverter(jailbreak_template=jailbreak)
        attack_config = AttackConverterConfig(
            request_converters=PromptConverterConfiguration.from_converters(converters=[converter]),
        )
    else:
        attack_config = AttackConverterConfig()

    scoring_config = AttackScoringConfig(objective_scorer=objective_scorer)
    attack = PromptSendingAttack(
        objective_target=adapter,
        attack_converter_config=attack_config,
        attack_scoring_config=scoring_config,
    )
    return await attack.execute_async(objective=objective)


def _filter_by_families(cases: list[dict[str, Any]], families: set[str] | None) -> list[dict[str, Any]]:
    if not families:
        return cases
    return [c for c in cases if str(c.get("family", "")) in families]


def _csv_fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    """合并所有结果行的键，避免首行缺字段导致 DictWriter 报错。"""
    ordered: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                ordered.append(k)
    return ordered


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    labels = ("attack_succeeded", "refused", "safe_but_incorrect", "normal_response", "execution_error")

    def bucket(rows: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(rows)
        counts = {lb: sum(1 for r in rows if r.get("final_label") == lb) for lb in labels}
        succ = counts["attack_succeeded"]
        ref = counts["refused"]
        return {
            "total": total,
            **{lb: counts[lb] for lb in labels},
            "success_rate": (succ / total) if total else 0.0,
            "refusal_rate": (ref / total) if total else 0.0,
        }

    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_agent[str(r.get("agent_id", ""))].append(r)
        by_family[str(r.get("attack_family", ""))].append(r)

    return {
        "summary_by_agent": {k: bucket(v) for k, v in sorted(by_agent.items())},
        "summary_by_family": {k: bucket(v) for k, v in sorted(by_family.items())},
        "summary_overall": bucket(records),
    }


async def run_experiment(
    *,
    experiment_id: str,
    agents_yaml: Path,
    bench_path: Path,
    taxonomy_path: Path,
    families_filter: set[str] | None,
    llm_judge: bool = False,
    llm_judge_override: bool = False,
    agent_pools_path: Path = DEFAULT_AGENT_POOLS,
    agent_ids_filter: list[str] | None = None,
    pool_name: str | None = None,
    pool_rotate_index: int | None = None,
    pool_failover: str | None = None,
    jailbreak_converter_families: set[str] | None = None,
) -> list[dict[str, Any]]:
    _load_dotenv()
    agents_all = load_agents_registry(agents_yaml)
    if not agents_all:
        print("No agents in registry.", file=sys.stderr)
        return []
    pools_data = load_agent_pools(agent_pools_path)
    agents, selection_meta = resolve_experiment_agents(
        agents_all,
        ROOT,
        pools_data,
        agent_ids=agent_ids_filter,
        pool_name=pool_name or None,
        pool_rotate_index=pool_rotate_index,
        pool_failover=pool_failover or None,
    )
    if not agents:
        print("No agents to run (filter matched nothing or pool unhealthy).", file=sys.stderr)
        print(f"  selection_meta: {selection_meta}", file=sys.stderr)
        return []
    print(f"Agent selection: {selection_meta}")
    taxonomy = load_taxonomy(taxonomy_path)
    full_bench = load_attack_bench(bench_path)
    if not full_bench:
        print("No attack bench rows; run: python build_attack_bench.py", file=sys.stderr)
        return []

    try:
        CentralMemory.get_memory_instance()
    except ValueError:
        CentralMemory.set_memory_instance(SQLiteMemory(db_path=":memory:"))

    exp_dir = EXPERIMENTS_DIR / experiment_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    results_json = exp_dir / "run_results.json"
    results_csv = exp_dir / "run_results.csv"
    summary_json = exp_dir / "run_summary.json"

    results: list[dict[str, Any]] = []

    for spec in agents:
        agent_id = spec.id
        print(f"--- Agent: {agent_id} ---")

        val_errs = validate_agent_spec(spec, ROOT)
        if val_errs:
            err = "validation: " + "; ".join(val_errs)
            print(f"  skip: {err}")
            ts = datetime.now(timezone.utc).isoformat()
            results.append(
                {
                    "experiment_id": experiment_id,
                    "agent_id": agent_id,
                    "agent_tags": get_agent_tags(spec),
                    "target_kind": "http",
                    "attack_id": "",
                    "attack_family": "",
                    "delivery_mode": "",
                    "prompt_sent": "",
                    "agent_reply": "",
                    "attack_success": False,
                    "refusal_detected": False,
                    "task_deviation": True,
                    "final_label": "execution_error",
                    "scorer_type": "",
                    "error": err,
                    "defense_enabled": spec.defense.enabled,
                    "defense_profile": spec.defense.profile,
                    "benchmark_included": is_benchmark_target(spec),
                    "timestamp": ts,
                }
            )
            continue

        rt = spec.runtime
        if rt is None or rt.deployment != "local_http":
            err = "runner v1 only supports runtime.deployment=local_http"
            print(f"  skip: {err}")
            ts = datetime.now(timezone.utc).isoformat()
            results.append(
                {
                    "experiment_id": experiment_id,
                    "agent_id": agent_id,
                    "agent_tags": get_agent_tags(spec),
                    "target_kind": "http",
                    "attack_id": "",
                    "attack_family": "",
                    "delivery_mode": "",
                    "prompt_sent": "",
                    "agent_reply": "",
                    "attack_success": False,
                    "refusal_detected": False,
                    "task_deviation": True,
                    "final_label": "execution_error",
                    "scorer_type": "",
                    "error": err,
                    "defense_enabled": spec.defense.enabled,
                    "defense_profile": spec.defense.profile,
                    "benchmark_included": is_benchmark_target(spec),
                    "timestamp": ts,
                }
            )
            continue

        try:
            http_target = build_http_target_from_spec(spec)
            if not http_target.healthcheck():
                raise RuntimeError("HTTP healthcheck failed")
        except Exception as e:
            err = f"build_http_target: {type(e).__name__}: {e}"
            print(f"  {err[:400]}")
            ts = datetime.now(timezone.utc).isoformat()
            results.append(
                {
                    "experiment_id": experiment_id,
                    "agent_id": agent_id,
                    "agent_tags": get_agent_tags(spec),
                    "target_kind": "http",
                    "attack_id": "",
                    "attack_family": "",
                    "delivery_mode": "",
                    "prompt_sent": "",
                    "agent_reply": "",
                    "attack_success": False,
                    "refusal_detected": False,
                    "task_deviation": True,
                    "final_label": "execution_error",
                    "scorer_type": "",
                    "error": err,
                    "defense_enabled": spec.defense.enabled,
                    "defense_profile": spec.defense.profile,
                    "benchmark_included": is_benchmark_target(spec),
                    "timestamp": ts,
                }
            )
            continue

        adapter = PyRITAdapter(
            dynamic_target=http_target,
            run_param_name=rt.input_key,
        )

        cases = select_attack_cases_for_agent(spec, full_bench, taxonomy)
        cases = _filter_by_families(cases, families_filter)

        for row in cases:
            scorer = scorer_from_bench_row(row)
            delivery = row.get("delivery_mode") or "direct_input"
            family = str(row.get("family") or "")

            jb_extra = jailbreak_converter_families or set()
            bench_jb = row.get("use_jailbreak_converter")
            if bench_jb is None:
                bench_jb = family == "jailbreak_rewrite"
            else:
                bench_jb = bool(bench_jb)
            use_jb = bench_jb or (family in jb_extra)
            prompt_for_attack = str(row.get("prompt") or "")
            poison_ctx: dict[str, Any] = {}

            if delivery == "environment_poisoning":
                case_for_poison = dict(row)
                case_for_poison["_experiment_id"] = experiment_id
                ptype = row.get("poisoner_type")
                poisoner = get_poisoner(ptype)
                if poisoner:
                    try:
                        poison_ctx = poisoner.prepare(_agent_spec_dict(spec), case_for_poison)
                    except Exception as e:
                        poison_ctx = {"_poison_error": f"{type(e).__name__}: {e}"}
                prompt_for_attack = str(row.get("trigger_prompt") or "")

            exec_err = ""
            result = None
            try:
                result = await execute_attack_case(
                    adapter=adapter,
                    objective=prompt_for_attack,
                    attack_family=family,
                    objective_scorer=scorer,
                    use_jailbreak_converter=use_jb,
                )
            except Exception as e:
                exec_err = f"attack: {type(e).__name__}: {e}"
            finally:
                if delivery == "environment_poisoning":
                    ptype = row.get("poisoner_type")
                    poisoner = get_poisoner(ptype)
                    if poisoner and poison_ctx:
                        try:
                            poisoner.cleanup(
                                _agent_spec_dict(spec),
                                dict(row),
                                poison_ctx,
                            )
                        except Exception:
                            pass

            agent_reply = _pyrit_result_reply(result)
            if not agent_reply and adapter.last_response_value:
                agent_reply = adapter.last_response_value[:4000]

            structured = compute_structured_outcome(
                attack_case=row,
                agent_reply=agent_reply,
                execution_error=exec_err or (adapter.last_error or ""),
                pyrit_scorer_success=_pyrit_scorer_bool(result),
            )

            prompt_sent = (adapter.last_request_value or prompt_for_attack or "")[:4000]
            ts = datetime.now(timezone.utc).isoformat()

            rec = {
                "experiment_id": experiment_id,
                "agent_id": agent_id,
                "agent_tags": get_agent_tags(spec),
                "target_kind": "http",
                "attack_id": row.get("attack_id", ""),
                "attack_family": family,
                "delivery_mode": delivery,
                "prompt_sent": prompt_sent,
                "agent_reply": agent_reply[:4000],
                "attack_success": structured["attack_success"],
                "refusal_detected": structured["refusal_detected"],
                "task_deviation": structured["task_deviation"],
                "final_label": structured["final_label"],
                "rule_final_label": structured["final_label"],
                "scorer_type": row.get("scorer_type", ""),
                "error": exec_err or (adapter.last_error or ""),
                "defense_enabled": spec.defense.enabled,
                "defense_profile": spec.defense.profile,
                "benchmark_included": is_benchmark_target(spec),
                "timestamp": ts,
                "pyrit_scorer_success": structured.get("pyrit_scorer_success"),
                "poisoner_type": row.get("poisoner_type"),
                "jailbreak_converter_used": use_jb,
            }

            judge_on = (llm_judge or is_llm_judge_enabled()) and structured.get(
                "final_label"
            ) != "execution_error" and (agent_reply or "").strip()
            if judge_on:
                llm_out = await asyncio.to_thread(
                    deepseek_judge_sync,
                    attack_case=dict(row),
                    prompt_sent=prompt_sent,
                    agent_reply=agent_reply[:4000],
                    rule_outcome=dict(structured),
                )
                rec.update({k: v for k, v in llm_out.items() if str(k).startswith("llm")})
                if llm_judge_override and llm_out.get("llm_final_label"):
                    rec["final_label"] = llm_out["llm_final_label"]
                    rec["attack_success"] = bool(llm_out.get("llm_attack_success"))
                    rec["refusal_detected"] = bool(llm_out.get("llm_refusal_detected"))
                    if rec["final_label"] == "refused":
                        rec["task_deviation"] = False
                    elif rec["final_label"] == "normal_response":
                        rec["task_deviation"] = False
                    elif rec["final_label"] == "execution_error":
                        rec["task_deviation"] = True
                    else:
                        rec["task_deviation"] = True

            results.append(rec)
            status = rec["final_label"]
            llm_note = ""
            if rec.get("llm_final_label") and not llm_judge_override:
                llm_note = f" [LLM:{rec['llm_final_label']}]"
            elif rec.get("llm_error") and not rec.get("llm_skipped"):
                llm_note = f" [LLM-err]"
            print(f"  {row.get('attack_id')} {status}{llm_note}")

    summary = _summarize(results)
    summary["experiment_meta"] = {
        **selection_meta,
        "experiment_id": experiment_id,
        "families_filter": sorted(families_filter) if families_filter else None,
        "llm_judge": llm_judge,
        "llm_judge_override": llm_judge_override,
        "jailbreak_converter_extra_families": sorted(jailbreak_converter_families)
        if jailbreak_converter_families
        else [],
    }

    results_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if results:
        keys = _csv_fieldnames(results)
        with open(results_csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys, restval="")
            w.writeheader()
            w.writerows(results)

    print(f"\nWrote {results_json} ({len(results)} rows)")
    print(f"Wrote {summary_json}")
    return results


def main() -> None:
    p = argparse.ArgumentParser(description="HTTP Agent red team runner v1")
    p.add_argument(
        "--experiment-id",
        default="",
        help="实验目录名；默认自动生成 UUID",
    )
    p.add_argument("--agents-yaml", type=Path, default=DEFAULT_AGENTS_YAML)
    p.add_argument("--bench", type=Path, default=DEFAULT_BENCH)
    p.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    p.add_argument(
        "--families",
        default="",
        help="仅运行指定 family，逗号分隔，如 benign_control,direct_prompt_injection",
    )
    p.add_argument(
        "--llm-judge",
        action="store_true",
        help="启用 DeepSeek 语义裁判（需 DEEPSEEK_API_KEY；也可用环境变量 LLM_JUDGE_ENABLED=1）",
    )
    p.add_argument(
        "--llm-judge-override",
        action="store_true",
        help="用 LLM 的 llm_final_label 覆盖 final_label / attack_success / refusal_detected",
    )
    p.add_argument(
        "--agent-pools-yaml",
        type=Path,
        default=DEFAULT_AGENT_POOLS,
        help="agent 池配置，默认 configs/agent_pools.yaml",
    )
    p.add_argument(
        "--agent-ids",
        default="",
        help="只评测这些 agent id，逗号分隔（可与 --pool 求交）",
    )
    p.add_argument(
        "--pool",
        default="",
        help="使用 agent_pools.yaml 中该池的 id 列表（顺序即优先级）",
    )
    p.add_argument(
        "--pool-rotate-index",
        type=int,
        default=None,
        help="与 --pool 合用：只跑 pool[id %% len(pool)]，用于按天/按任务轮换占坑",
    )
    p.add_argument(
        "--pool-failover",
        default="",
        help="从该池中按顺序找第一个 HTTP 健康的 agent，只跑它（替补）",
    )
    p.add_argument(
        "--jailbreak-converter-families",
        default="",
        help="除 jailbreak_rewrite 外，对这些 family 也启用 TextJailbreakConverter（换壳，自适应时常与 adaptive_planner 联用）",
    )
    args = p.parse_args()

    exp_id = args.experiment_id.strip() or str(uuid.uuid4())
    fams = {x.strip() for x in args.families.split(",") if x.strip()} or None
    llm_on = bool(args.llm_judge) or is_llm_judge_enabled()
    aid_list = [x.strip() for x in args.agent_ids.split(",") if x.strip()] or None
    pool_n = args.pool.strip() or None
    pf = args.pool_failover.strip() or None
    if args.pool_rotate_index is not None and not pool_n:
        print("Warning: --pool-rotate-index ignored without --pool", file=sys.stderr)

    jb_conv: set[str] | None = None
    if args.jailbreak_converter_families.strip():
        jb_conv = {x.strip() for x in args.jailbreak_converter_families.split(",") if x.strip()}

    asyncio.run(
        run_experiment(
            experiment_id=exp_id,
            agents_yaml=args.agents_yaml,
            bench_path=args.bench,
            taxonomy_path=args.taxonomy,
            families_filter=fams,
            llm_judge=llm_on,
            llm_judge_override=bool(args.llm_judge_override),
            agent_pools_path=args.agent_pools_yaml,
            agent_ids_filter=aid_list,
            pool_name=pool_n,
            pool_rotate_index=args.pool_rotate_index,
            pool_failover=pf,
            jailbreak_converter_families=jb_conv,
        )
    )


if __name__ == "__main__":
    main()
