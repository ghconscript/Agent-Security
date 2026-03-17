from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from langchain.agents import create_agent
from dotenv import load_dotenv
import os

from langchain_deepseek import ChatDeepSeek  # 需要在该项目 venv 中 pip install langchain-deepseek

load_dotenv()


# defining the tool that LLM can call
def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"


# 创建 DeepSeek LLM 实例（使用 DEEPSEEK_API_KEY）
llm = ChatDeepSeek(
    model="deepseek-chat",
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
)

# Creating an agent：新版 create_agent 接收的是模型对象，而不是 model_provider 之类的参数
agent = create_agent(
    model=llm,
    tools=[get_weather],
    system_prompt="You are a helpful assistant",
)


app = FastAPI()


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def root():
    return {"message": "Welcome to your first agent"}


@app.post("/chat")
def chat(request: ChatRequest):
    result = agent.invoke({"messages": [{"role": "user", "content": request.message}]})
    return {"reply": result["messages"][-1].content}


def main():
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()