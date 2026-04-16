"""
SubprocessTarget：在目标仓库自己的虚拟环境中，通过子进程运行 Agent 并交互。

约定目标仓库提供一个 subprocess_entry.py，协议为:
  stdin:  {"input": "..."}
  stdout: {"output": "..."}
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class SubprocessTarget:
    def __init__(
        self,
        repo_path: str | Path,
        venv_python: str,
        entry_script: str = "subprocess_entry.py",
        *,
        identifier: str = "",
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.venv_python = Path(venv_python).resolve()
        self.entry_script = entry_script
        self.identifier = identifier

    def run(self, message: str, **kwargs: Any) -> str:
        payload = json.dumps({"input": message, **kwargs}, ensure_ascii=False)
        proc = subprocess.run(
            [str(self.venv_python), self.entry_script],
            input=payload.encode("utf-8"),
            cwd=str(self.repo_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(f"SubprocessTarget failed: {stderr}")
        data = json.loads(proc.stdout.decode("utf-8") or "{}")
        return str(data.get("output", data))

    def healthcheck(self) -> bool:
        if not self.venv_python.is_file():
            return False
        script = self.repo_path / self.entry_script
        if not script.is_file():
            return False
        try:
            self.run("__registry_ping__")
            return True
        except Exception:
            return False

    def describe(self) -> dict[str, Any]:
        return {
            "target_kind": "subprocess",
            "identifier": self.identifier or str(self.repo_path),
            "entry_file": self.entry_script,
            "entry_name": "subprocess_entry",
            "run_param_name": "message",
        }
