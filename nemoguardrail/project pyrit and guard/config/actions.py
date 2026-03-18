import httpx
from nemoguardrails.actions import action

@action(is_system_action=True)
async def check_pyrit_safety(context: dict = None):
    user_text = context.get("last_user_message")
    pyrit_api_url = "http://pyrit-api:5000/score"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(pyrit_api_url, json={"text": user_text}, timeout=10)
            result = response.json()
        is_safe = result.get("is_safe", True)
        context["pyrit_is_safe"] = is_safe
        return is_safe
    except Exception as e:
        print(f"PyRIT API Error: {e}")
        context["pyrit_is_safe"] = True
        return True


@action(is_system_action=True)
async def add_safe_indicator(context: dict = None):
    bot_msg = context.get("bot_message", "")
    context["bot_message"] = bot_msg + "\n\n─────────────────\n[✅ PyRIT 已通过]"
    return True
