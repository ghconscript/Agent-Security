"""
从 configs/attack_taxonomy.yaml + attack_templates/*.jsonl 生成统一基准 attack_bench.jsonl。
补齐 delivery_mode、poisoner_type、default_scorer；校验 family 存在于 taxonomy。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = ROOT / "attack_templates"
TAXONOMY_PATH = ROOT / "configs" / "attack_taxonomy.yaml"
OUT_PATH = ROOT / "attack_bench.jsonl"

_LEGACY_SCORER_MAP = {
    "nonempty": "non_empty_response",
    "refusal_aware": "refusal_aware_attack_success",
    "substring": "substring_success",
}


def _family_map(tax: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for fam in tax.get("attack_families") or []:
        fid = fam.get("id")
        if fid:
            out[str(fid)] = fam
    return out


def _normalize_scorer_type(raw: str | None, default: str) -> str:
    s = (raw or "").strip()
    if not s:
        return default
    return _LEGACY_SCORER_MAP.get(s.lower(), s)


def main() -> int:
    tax_raw = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8")) or {}
    families_meta = _family_map(tax_raw)

    rows_out: list[dict] = []
    errors: list[str] = []

    for path in sorted(TEMPLATES_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            fam = str(rec.get("family") or "")
            meta = families_meta.get(fam)
            if not meta:
                errors.append(f"{path.name}: unknown family {fam!r} in template {rec.get('id')}")
                continue

            delivery = meta.get("delivery_mode") or "direct_input"
            default_scorer = str(meta.get("default_scorer") or "refusal_aware_attack_success")
            poisoner_type = meta.get("poisoner_type")

            st = _normalize_scorer_type(rec.get("scorer_type"), default_scorer)

            use_jb = meta.get("use_jailbreak_converter")
            if use_jb is None:
                use_jb = fam == "jailbreak_rewrite"

            row: dict = {
                "attack_id": rec["id"],
                "family": fam,
                "delivery_mode": delivery,
                "poisoner_type": poisoner_type if delivery == "environment_poisoning" else None,
                "default_scorer": default_scorer,
                "use_jailbreak_converter": bool(use_jb),
                "expected_behavior": rec.get("expected_behavior", ""),
                "success_condition": rec.get("success_condition", ""),
                "scorer_type": st,
                "risk_level": rec.get("risk_level", ""),
                "notes": rec.get("notes", ""),
            }

            if delivery == "direct_input":
                row["prompt"] = rec.get("prompt", "")
            else:
                row["poison_payload"] = rec.get("poison_payload", "")
                row["trigger_prompt"] = rec.get("trigger_prompt", "")
                row["prompt"] = ""

            if rec.get("success_substring"):
                row["success_substring"] = rec["success_substring"]

            rows_out.append(row)

    OUT_PATH.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows_out) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(rows_out)} rows to {OUT_PATH}")
    if errors:
        print("Validation errors:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
