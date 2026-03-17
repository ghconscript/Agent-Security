import asyncio
from nemoguardrails import RailsConfig, LLMRails

async def main():
    config = RailsConfig.from_path("./config")
    rails = LLMRails(config)

    print("--- PyRIT + NeMo Guardrails 已启动 (输入 'quit' 退出) ---")

    # ====== 临时测试：硬编码输入，验证 PyRIT API 调用是否成功 ======
    test_input = "你好，今天天气怎么样？"
    print(f"用户(硬编码): {test_input}")
    response = await rails.generate_async(prompt=test_input)
    print(f"助手: {response}\n")
    print("--- 测试完成，程序退出 ---")
    return
    # ====== 测试结束 ======

    while True:
        user_input = input("用户: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            break

        response = await rails.generate_async(prompt=user_input)
        print(f"助手: {response}\n")

if __name__ == "__main__":
    # 解决 Docker 中 input() 可能导致的 EOFError
    try:
        asyncio.run(main())
    except EOFError:
        pass