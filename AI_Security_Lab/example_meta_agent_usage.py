"""
MetaAgent 与 DynamicTarget 使用示例。

依赖: pip install langchain langchain-deepseek langchain-core pydantic python-dotenv

========== API Key 写在哪（二选一）==========
方式1（推荐）：在项目根目录建 .env 文件，里面写一行：
  DEEPSEEK_API_KEY=sk-你的key
然后本脚本开头会 load_dotenv() 自动读。

方式2：在运行前在终端设环境变量（PowerShell）：
  $env:DEEPSEEK_API_KEY="sk-你的key"
"""

import os
from pathlib import Path

# 从项目根目录的 .env 里读 DEEPSEEK_API_KEY（有 python-dotenv 时）
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from meta_agent import MetaAgent, AgentEntryResult


def example_scan_and_detect():
    """扫描当前项目目录，用 LLM 检测 Agent 入口。"""
    repo = Path(__file__).resolve().parent

    meta = MetaAgent(repo, model="deepseek-chat", max_snippet_lines=300)
    result = meta.detect_entry()
    print("检测到的入口:", result.model_dump_json(indent=2))
    return meta, result


def example_build_and_run(meta: MetaAgent, entry_result: AgentEntryResult | None = None):
    """根据检测结果生成 DynamicTarget 并执行。"""
    DynamicTarget = meta.build_dynamic_target_class(entry_result)
    print("参数 schema:", DynamicTarget.get_params_schema())

    target = DynamicTarget()
    # 按 LLM 返回的 params 传入参数，例如:
    # out = target.run(message="hello", stream=False)
    # print(out)
    return DynamicTarget, target


def example_one_shot(repo_path: str | Path, **run_kwargs):
    """一键：扫描 → 检测 → 执行（需已知入口参数名）。"""
    from meta_agent import run_agent_from_repo
    return run_agent_from_repo(repo_path, model="deepseek-chat", **run_kwargs)


if __name__ == "__main__":
    # 仅做检测与生成 DynamicTarget，不实际调用 LLM 时可先注释掉 detect_entry
    meta, result = example_scan_and_detect()
    DynamicTarget, target = example_build_and_run(meta, result)
    # 实际调用: target.run(...)
