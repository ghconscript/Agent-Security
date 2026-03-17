from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class ChatReq(BaseModel):
    input: str


class ChatResp(BaseModel):
    output: str


@app.post("/chat", response_model=ChatResp)
def chat(req: ChatReq) -> ChatResp:
    # 模拟被攻击的 Agent：简单回显
    return ChatResp(output=f"dummy agent received: {req.input}")

