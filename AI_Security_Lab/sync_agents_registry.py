"""
读取 configs/agents.yaml，校验配置并对 HTTP target 做 healthcheck（不执行攻击）。
输出 artifacts/agents_registry_check.json / .csv

每行字段：id, base_url, path, healthcheck_result, error
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

from agent_registry import (
    build_http_target_from_spec,
    load_agents_registry,
    validate_agent_spec,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY = ROOT / "configs" / "agents.yaml"
ARTIFACTS = ROOT / "artifacts"
OUT_JSON = ARTIFACTS / "agents_registry_check.json"
OUT_CSV = ARTIFACTS / "agents_registry_check.csv"


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


def main() -> None:
    _load_dotenv()
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_REGISTRY
    agents = load_agents_registry(path)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for spec in agents:
        rt = spec.runtime
        base_url = (rt.base_url if rt else "") or ""
        apath = (rt.path if rt else "") or ""
        val_errs = validate_agent_spec(spec, ROOT)

        err_parts: list[str] = []
        if val_errs:
            err_parts.append("validation: " + "; ".join(val_errs))

        healthcheck_result = False
        if not val_errs and rt and rt.deployment == "local_http":
            try:
                t = build_http_target_from_spec(spec)
                healthcheck_result = bool(t.healthcheck())
                if not healthcheck_result:
                    err_parts.append("healthcheck failed")
            except Exception as e:
                err_parts.append(f"{type(e).__name__}: {e}")
        elif rt and rt.deployment != "local_http":
            err_parts.append(f"skipped: deployment={rt.deployment}")
        elif not rt:
            err_parts.append("missing runtime")

        rows.append(
            {
                "id": spec.id,
                "base_url": base_url,
                "path": apath,
                "healthcheck_result": healthcheck_result,
                "error": "; ".join(err_parts) if err_parts else "",
            }
        )

    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if rows:
        keys = list(rows[0].keys())
        with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    print(f"Wrote {OUT_JSON} ({len(rows)} agents)")
    print(f"Wrote {OUT_CSV}")


if __name__ == "__main__":
    main()
