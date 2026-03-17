"""
试验循环：对多个仓库依次调用 detect_entry，将结果（含人工核对字段 reason）写入 CSV/JSON。

用法：
  1. 在 REPO_PATHS 中填写待测仓库路径（或保持默认 demo_repo）。
  2. 确保 .env 或 .env.example 中配置了 DEEPSEEK_API_KEY。
  3. 运行：python experiment_batch_run.py
  4. 查看 experiment_results.json / experiment_results.csv。
"""

import json
import os
import sys
from pathlib import Path

# 加载 .env
_root = Path(__file__).resolve().parent
for _env_file in (_root / ".env", _root / ".env.example"):
    if _env_file.is_file():
        with open(_env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k:
                        os.environ.setdefault(k, v)
        break

# 待测仓库列表（请按实际路径修改）
REPO_PATHS = [
    _root / "demo_repo",
    # _root / "testing-agent",   # 若有克隆的 testing-agent 可取消注释
    # Path(r"D:\path\to\other_repo"),
]


def run_batch():
    import csv
    from datetime import datetime
    from meta_agent import MetaAgent, AgentEntryResult

    results: list[dict] = []
    out_dir = _root
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / "experiment_results.json"
    csv_path = out_dir / "experiment_results.csv"

    for repo_path in REPO_PATHS:
        repo_path = Path(repo_path).resolve()
        if not repo_path.is_dir():
            row = {
                "repo_path": str(repo_path),
                "error": "目录不存在",
                "entry_file": "",
                "entry_line": "",
                "entry_name": "",
                "params": "",
                "reason": "",
                "is_method": "",
            }
            results.append(row)
            print(f"跳过（非目录）: {repo_path}")
            continue

        print(f"检测入口: {repo_path}")
        try:
            meta = MetaAgent(repo_path, model="deepseek-chat", max_snippet_lines=500)
            entry = meta.detect_entry()
            assert isinstance(entry, AgentEntryResult)
            row = {
                "repo_path": str(repo_path),
                "error": "",
                "entry_file": entry.entry_file,
                "entry_line": entry.entry_line,
                "entry_name": entry.entry_name,
                "params": json.dumps([p.model_dump() for p in entry.params], ensure_ascii=False),
                "reason": entry.reason or "",
                "is_method": entry.is_method,
            }
            results.append(row)
            short_reason = (entry.reason or "")[:80] + ("..." if len(entry.reason or "") > 80 else "")
            print(f"  -> {entry.entry_file}:{entry.entry_line} {entry.entry_name} | reason: {short_reason}")
        except Exception as e:
            row = {
                "repo_path": str(repo_path),
                "error": str(e),
                "entry_file": "",
                "entry_line": "",
                "entry_name": "",
                "params": "",
                "reason": "",
                "is_method": "",
            }
            results.append(row)
            print(f"  -> 失败: {e}")

    # 写入 JSON（含完整结构，便于人工核对 reason）
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {"timestamp": ts, "repos": results},
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n已写入: {json_path}")

    # 写入 CSV
    if results:
        keys = list(results[0].keys())
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(results)
        print(f"已写入: {csv_path}")

    return results


if __name__ == "__main__":
    run_batch()
