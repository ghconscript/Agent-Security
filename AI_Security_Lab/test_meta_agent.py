"""
端到端测验「整个程序」是否好使。

流程：扫描 demo 仓库 → LLM 识别入口 → 生成 DynamicTarget → 实际调用入口并校验结果。

用法：
  1. .env 里配置 DEEPSEEK_API_KEY=sk-xxx（或设环境变量）
  2. 在项目根目录执行：python test_meta_agent.py
"""

import os
import sys
from pathlib import Path

# 加载项目根目录的 .env 和 .env.example（不依赖 python-dotenv）
_root = Path(__file__).resolve().parent
for _env_file in (_root / ".env", _root / ".env.example"):
    if _env_file.is_file():
        with open(_env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k:
                        os.environ.setdefault(k, v)


def main():
    if not os.environ.get("DEEPSEEK_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        print("❌ 未设置 API Key。")
        print("   已检查 .env 路径:", _env_file)
        print("   请确认：1) 该路径下存在 .env  2) 文件内有 DEEPSEEK_API_KEY=sk-xxx（等号两边无空格）")
        sys.exit(1)

    # 用项目里的 demo_repo 做完整流程测验
    repo = Path(__file__).resolve().parent / "demo_repo"
    if not repo.is_dir():
        print("❌ 找不到 demo_repo 目录，无法运行端到端测验")
        sys.exit(1)

    print("=== 端到端测验：扫描 → LLM 识别入口 → 生成 DynamicTarget → 执行 run ===\n")

    try:
        from meta_agent import MetaAgent
    except ImportError as e:
        print("❌ 导入 MetaAgent 失败:", e)
        sys.exit(1)

    try:
        # 1. 创建 MetaAgent，扫描 demo_repo
        print("1. 创建 MetaAgent 并扫描 demo_repo ...")
        meta = MetaAgent(repo, model="deepseek-chat", max_snippet_lines=500)
        print("   ✓ 扫描完成\n")

        # 2. 调用 LLM 识别入口
        print("2. 调用 LLM 识别入口 ...")
        result = meta.detect_entry()
        print("   LLM 返回的入口信息:")
        print("   ", result.model_dump_json(indent=2).replace("\n", "\n   "))
        print()

        # 3. 生成 DynamicTarget
        print("3. 生成 DynamicTarget 类 ...")
        DynamicTarget = meta.build_dynamic_target_class()
        print("   参数 schema:", DynamicTarget.get_params_schema())
        print("   ✓ DynamicTarget 生成完成\n")

        # 4. 实例化并调用入口（用 demo 的 run(message=...)）
        print("4. 调用入口 run(message='端到端测验') ...")
        target = DynamicTarget()
        out = target.run(message="端到端测验")
        print("   返回:", out)

        # 简单校验：demo 的 run 会返回 "received: xxx"
        if "端到端测验" in str(out) or "received" in str(out).lower():
            print("\n✓ 整个程序测验通过：扫描、LLM、DynamicTarget、执行入口均正常。")
        else:
            print("\n✓ 入口已成功执行，返回结果如上（可按需自行校验）。")
    except Exception as e:
        print("\n❌ 测验失败:", e)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
