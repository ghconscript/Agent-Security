import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from nemoguardrails.actions import action

_audit_path = Path(__file__).with_name("logs").joinpath("rail_audit.jsonl")


def _write_audit(event: dict):
    _audit_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(event)
    payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    with _audit_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

@action(is_system_action=True)
async def check_pyrit_safety_azure(context: dict = None):
    def _get_latest_user_text(ctx: dict) -> str:
        msgs = ctx.get("messages") if isinstance(ctx, dict) else None
        if isinstance(msgs, list):
            for m in reversed(msgs):
                if isinstance(m, dict) and m.get("role") == "user":
                    return m.get("content", "") or ""
        # [Modified 2026-03-26] Prefer current user_message over last_user_message to avoid stale blocking
        return (ctx or {}).get("user_message") or (ctx or {}).get("last_user_message") or ""

    ctx = context or {}
    user_text = _get_latest_user_text(ctx)
    # [Modified 2026-03-26] Debug: inspect context shape and selected user text source
    try:
        msgs = ctx.get("messages") if isinstance(ctx, dict) else None
        msgs_len = len(msgs) if isinstance(msgs, list) else None
        last_user_message = ctx.get("last_user_message") if isinstance(ctx, dict) else None
        user_message = ctx.get("user_message") if isinstance(ctx, dict) else None
        text_hash = hashlib.sha256((user_text or "").encode("utf-8", errors="replace")).hexdigest()
        print(
            "[pyrit] ctx_keys=%s msgs_len=%s last_user_message=%r user_message=%r"
            % (list(ctx.keys()) if isinstance(ctx, dict) else None, msgs_len, last_user_message, user_message)
        )
        print(f"[pyrit] check_pyrit_safety user_text: {user_text!r} sha256={text_hash}")
    except Exception as _e:
        print(f"[pyrit] debug_log_error: {_e}")
    pyrit_api_url = "http://pyrit-api:5000/score"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(pyrit_api_url, json={"text": user_text, "mode": "input", "scorer": "azure"}, timeout=10)
            result = response.json()
        is_safe = result.get("is_safe", True)
        context["pyrit_is_safe"] = is_safe
        _write_audit(
            {
                "direction": "input",
                "text": user_text,
                "decision": "allow" if is_safe else "deny",
                "scorer": "azure",
                "bridge_result": result,
            }
        )
        return is_safe
    except Exception as e:
        print(f"PyRIT API Error: {e}")
        context["pyrit_is_safe"] = True
        _write_audit(
            {
                "direction": "input",
                "text": user_text,
                "decision": "allow",
                "scorer": "azure",
                "error": str(e),
            }
        )
        return True


@action(is_system_action=True)
async def check_pyrit_safety_category_output(context: dict = None):
    def _get_latest_bot_text(ctx: dict) -> str:
        msgs = ctx.get("messages") if isinstance(ctx, dict) else None
        if isinstance(msgs, list):
            for m in reversed(msgs):
                if isinstance(m, dict) and m.get("role") == "assistant":
                    return m.get("content", "") or ""
        return (ctx or {}).get("bot_message") or (ctx or {}).get("last_bot_message") or ""

    ctx = context or {}
    bot_text = _get_latest_bot_text(ctx)
    try:
        msgs = ctx.get("messages") if isinstance(ctx, dict) else None
        msgs_len = len(msgs) if isinstance(msgs, list) else None
        last_user_message = ctx.get("last_bot_message") if isinstance(ctx, dict) else None
        user_message = ctx.get("bot_message") if isinstance(ctx, dict) else None
        text_hash = hashlib.sha256((bot_text or "").encode("utf-8", errors="replace")).hexdigest()
        print(
            "[pyrit] ctx_keys=%s msgs_len=%s last_bot_message=%r bot_message=%r"
            % (list(ctx.keys()) if isinstance(ctx, dict) else None, msgs_len, last_user_message, user_message)
        )
        print(f"[pyrit] check_pyrit_safety output_text: {bot_text!r} sha256={text_hash}")
    except Exception as _e:
        print(f"[pyrit] debug_log_error: {_e}")
    pyrit_api_url = "http://pyrit-api:5000/score"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(pyrit_api_url, json={"text": bot_text, "mode": "output", "scorer": "self_ask_category"}, timeout=10)
            result = response.json()
        is_safe = result.get("is_safe", True)
        context["pyrit_is_safe"] = is_safe
        _write_audit(
            {
                "direction": "output",
                "text": bot_text,
                "decision": "allow" if is_safe else "deny",
                "scorer": "self_ask_category",
                "bridge_result": result,
            }
        )
        return is_safe
    except Exception as e:
        print(f"PyRIT API Error: {e}")
        context["pyrit_is_safe"] = True
        _write_audit(
            {
                "direction": "output",
                "text": bot_text,
                "decision": "allow",
                "scorer": "self_ask_category",
                "error": str(e),
            }
        )
        return True


@action(is_system_action=True)
async def add_safe_indicator(context: dict = None):
    bot_msg = context.get("bot_message", "")
    return bot_msg
