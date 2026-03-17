"""供 MetaAgent 端到端测验用的最小 demo：只有一个入口函数。"""

def run(message: str = "hello") -> str:
    """Agent 入口：接收一条消息，返回回复。"""
    return f"received: {message}"
