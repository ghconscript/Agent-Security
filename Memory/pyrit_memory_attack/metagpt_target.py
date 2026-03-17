# 确保从 pyrit_memory_attack 运行时能找到 Agent-Memory-Poisoning 下的 metagpt_attack_poc
import sys
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parent.parent / "Agent-Memory-Poisoning"
if _AGENT_ROOT.exists() and str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

from metagpt_attack_poc.pyrit_entrypoints import (
    arun_data_interpreter,
    run_experiment,
)

# 可选：若已安装 PyRIT 且版本带 targets，可继承其 Target 以接入 orchestrator
try:
    from pyrit.targets.base_target import Target as _PyRITTarget
    _Base = _PyRITTarget
except Exception:
    _Base = object


class MetaGPTAgentTarget(_Base):
    """
    把 MetaGPT 的 DataInterpreter 封装成可调用的 Target：
    - input: 攻击 prompt（字符串）
    - output: agent 的完整回复（字符串）
    与 PyRIT 的 PromptSendingOrchestrator 用法兼容（提供 async send(prompt) -> str）。
    """

    async def send(self, prompt: str) -> str:
        # 直接 await 异步入口，避免在已有事件循环中再调用 asyncio.run
        return await arun_data_interpreter(prompt)


class MetaGPTExperimentTarget(_Base):
    """
    把四个攻击实验脚本封装成 Target：
    - input: 实验名，如 "exp3"、"exp4"、"schema_spoof"
    - output: 对应实验脚本的 stdout+stderr
    """

    async def send(self, prompt: str) -> str:
        exp_name = prompt.strip()
        return run_experiment(exp_name)