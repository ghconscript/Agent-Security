from http_target import HttpTarget


def main() -> None:
    target = HttpTarget(
        base_url="http://127.0.0.1:8000",
        path="/chat",
        input_key="message",
    )
    out = target.run("这是一次 HttpTarget 测试")
    print("Agent 输出:", out)


if __name__ == "__main__":
    main()

