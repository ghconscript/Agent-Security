from pathlib import Path
import json
from datetime import datetime, timezone
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI()

_scorers: dict[str, Any] = {}
_audit_path = Path(__file__).with_name("logs").joinpath("bridge_api_audit.jsonl")


def _load_pyrit_env():
    from dotenv import load_dotenv

    candidates = [
        Path.home() / ".pyrit" / ".env",
        Path("/home/vscode/.pyrit/.env"),
        Path("/root/.pyrit/.env"),
    ]

    for env_path in candidates:
        if env_path.exists():
            load_dotenv(env_path)
            return str(env_path)
    return None


def _ensure_memory():
    from pyrit.memory import CentralMemory, SQLiteMemory

    CentralMemory.set_memory_instance(SQLiteMemory())


def _write_audit(event: dict[str, Any]):
    _audit_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(event)
    payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    with _audit_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_category_safe(value: Any, rationale: Any = None) -> bool:
    text = " ".join([_normalize_text(value), _normalize_text(rationale)])
    unsafe_terms = [
        "unsafe",
        "unsafe_content",
        "harm",
        "violence",
        "sexual",
        "jailbreak",
        "prompt injection",
        "policy violation",
        "blocked",
        "malicious",
        "self-harm",
        "hate",
        "abuse",
        "weapon",
        "drug",
        "fraud",
    ]
    safe_terms = [
        "safe",
        "allowed",
        "benign",
        "non-harm",
        "non harmful",
        "compliant",
    ]
    if any(term in text for term in unsafe_terms):
        return False
    if any(term in text for term in safe_terms):
        return True
    return False


def _decide_is_safe(score, value):
    if score.score_type == "true_false":
        return value is not True
    if score.score_type == "float_scale":
        try:
            return float(value) <= 0
        except Exception:
            return False
    if score.score_type == "category":
        return _is_category_safe(value, getattr(score, "score_rationale", None))
    return False


def get_scorer(name: str):
    if name not in _scorers:
        _load_pyrit_env()
        _ensure_memory()

        if name == "azure":
            from pyrit.score import AzureContentFilterScorer

            _scorers[name] = AzureContentFilterScorer()
        elif name == "self_ask_true_false":
            from pyrit.prompt_target import OpenAIChatTarget
            from pyrit.score import SelfAskTrueFalseScorer

            chat_target = OpenAIChatTarget()
            _scorers[name] = SelfAskTrueFalseScorer(chat_target=chat_target)
        elif name == "self_ask_category":
            from pyrit.prompt_target import OpenAIChatTarget
            from pyrit.score import SelfAskCategoryScorer

            chat_target = OpenAIChatTarget()
            _scorers[name] = SelfAskCategoryScorer(chat_target=chat_target)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported scorer: {name}")
    return _scorers[name]


class Content(BaseModel):
    text: str
    mode: Literal["input", "output"] = Field(default="output")
    scorer: Literal["azure", "self_ask_true_false", "self_ask_category"] = Field(default="azure")


@app.post("/score")
async def get_score(data: Content):
    try:
        scorer_name = data.scorer
        if data.mode == "output" and scorer_name == "azure":
            scorer_name = "self_ask_category"

        scorer = get_scorer(scorer_name)
        scores = await scorer.score_text_async(data.text)

        is_safe = True
        detailed_results = []
        score_values = []

        for a in scores:
            try:
                value = a.get_value()
            except Exception:
                value = a.score_value

            cur_info = {
                "category": a.score_category,
                "score_type": a.score_type,
                "value": value,
                "value_description": a.score_value_description,
                "reason": a.score_rationale,
            }

            if not _decide_is_safe(a, value):
                is_safe = False

            detailed_results.append(cur_info)
            score_values.append(value)

        _write_audit(
            {
                "mode": data.mode,
                "scorer": scorer_name,
                "is_safe": is_safe,
                "text": data.text,
                "details": detailed_results,
                "score_value": score_values,
            }
        )

        return {
            "is_safe": is_safe,
            "mode": data.mode,
            "scorer": scorer_name,
            "score_value": score_values,
            "details": detailed_results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
