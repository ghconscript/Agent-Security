# GitHub Agent 自动化工具

这是一个Python工具，用于自动化搜索、克隆和运行GitHub上的agent项目。

## 功能特性

- 🔍 **搜索GitHub项目**: 使用GitHub API搜索agent相关项目
- 📥 **自动克隆**: 批量克隆找到的项目
- 📦 **依赖安装**: 自动检测并安装项目依赖（requirements.txt, setup.py, pyproject.toml）
- 🚀 **自动运行**: 尝试自动运行项目（可选）
- 💾 **结果保存**: 将搜索结果保存为JSON文件

## 安装

```bash
pip install -r requirements.txt
```

## 使用方法

### 基本使用

```bash
# 搜索并克隆5个Python agent项目
python github_agent_automation.py

# 搜索特定关键词
python github_agent_automation.py --keyword "autonomous agent"

# 指定编程语言
python github_agent_automation.py --language "javascript"

# 使用GitHub Token提高API限制（推荐）
python github_agent_automation.py --token YOUR_GITHUB_TOKEN

# 只搜索不克隆
python github_agent_automation.py --no-clone

# 克隆并运行项目
python github_agent_automation.py --run

# 自定义输出目录
python github_agent_automation.py --output my_agents

# 处理更多项目
python github_agent_automation.py --max 10
```

### 作为Python模块使用

```python
from github_agent_automation import GitHubAgentAutomation

# 创建实例
automation = GitHubAgentAutomation(
    github_token="YOUR_TOKEN",  # 可选
    output_dir="my_agents"
)

# 搜索项目
results = automation.search_agents(keyword="agent", language="python", per_page=10)

# 克隆单个项目
automation.clone_repository(
    clone_url="https://github.com/user/repo.git",
    repo_name="repo"
)

# 完整流程
automation.process_agents(
    keyword="agent",
    language="python",
    clone=True,
    install=True,
    run=False,
    max_repos=5
)
```

## GitHub Token设置（可选但推荐）

使用GitHub Token可以提高API请求限制（从60次/小时提升到5000次/小时）：

1. 访问 https://github.com/settings/tokens
2. 生成新的Personal Access Token
3. 使用 `--token` 参数或在代码中传入token

## 注意事项

- 确保已安装 `git` 命令行工具
- 确保已安装 `pip` 和 `python`
- 某些项目可能需要特定的环境配置才能运行
- 运行项目前请仔细阅读项目的README文件

## 示例输出

```
🔍 正在搜索GitHub上的 'agent' 项目...
✅ 找到 10 个项目
💾 结果已保存到 github_agents/search_results.json

============================================================
📋 搜索结果:
============================================================

1. microsoft/autogen
   ⭐ Stars: 25000 | 🍴 Forks: 3000
   📝 AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation
   🔗 https://github.com/microsoft/autogen

...
```

## 许可证

MIT License
