#!/usr/bin/env python
"""
子进程入口：从 stdin 读取 JSON，调用 testing-agent 自己的 run_agent，然后把结果写回 stdout。

期望输入: {"input": "..."}，输出: {"output": "..."}。
"""

import json
import sys

from agent.agent import run_agent


def main() -> None:
    data = json.loads(sys.stdin.read() or "{}")
    user_input = data.get("input", "")
    # 这里可以按需支持 provider / use_streaming / agent_type 等额外参数
    result = run_agent(user_input=user_input)
    sys.stdout.write(json.dumps({"output": str(result)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

