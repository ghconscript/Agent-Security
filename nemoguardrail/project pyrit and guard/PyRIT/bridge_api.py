from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import asyncio
import os

app = FastAPI()

# 延迟初始化：在第一次请求时才创建 scorer，避免模块加载时崩溃
_scorer = None

def get_scorer():
    global _scorer
    if _scorer is None:
        # 加载 .pyrit/.env 中的环境变量
        from dotenv import load_dotenv
        load_dotenv("/root/.pyrit/.env")

        from pyrit.memory import CentralMemory, SQLiteMemory
        from pyrit.prompt_target import OpenAIChatTarget
        from pyrit.score import SelfAskTrueFalseScorer

        CentralMemory.set_memory_instance(SQLiteMemory())

        # OpenAIChatTarget 会自动从环境变量读取：
        #   OPENAI_CHAT_ENDPOINT, OPENAI_CHAT_KEY, OPENAI_CHAT_MODEL
        chat_target = OpenAIChatTarget()

        _scorer = SelfAskTrueFalseScorer(chat_target=chat_target)
    return _scorer

class Content(BaseModel):
    text: str

@app.post("/score")
async def get_score(data: Content):
    try:
        scorer = get_scorer()
        scores = await scorer.score_text_async(data.text)
        is_safe = scores[0].score_value == "true"
        return {"is_safe": is_safe, "score_value": scores[0].score_value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
