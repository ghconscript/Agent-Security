# PyRIT + MetaGPT 记忆投毒实验

本目录用于在 **PyRIT** 框架下运行 **Agent-Memory-Poisoning** 的投毒攻击与实验。

## 目录结构

```
memory_attack/
├── Agent-Memory-Poisoning/     # MetaGPT 投毒项目（LLM/实验脚本）
└── pyrit_memory_attack/        # 本目录
    ├── metagpt_target.py       # PyRIT 自定义 Target（调用 DataInterpreter / 实验脚本）
    ├── run_metagpt_scenario.py # 场景入口脚本
    └── README.md               # 本说明
```

---

## 接下来每一步怎么做

### 第 1 步：确认环境

在 **同一台电脑、同一个虚拟环境** 里完成：

1. **安装并注册 Agent-Memory-Poisoning**

   ```bash
   cd C:\Users\Lenovo\Desktop\memory_attack\Agent-Memory-Poisoning
   pip install -e .
   ```

2. **安装 PyRIT**

   ```bash
   pip install pyrit
   ```

3. **检查能否导入**

   ```bash
   python -c "import pyrit; from metagpt_attack_poc.pyrit_entrypoints import run_data_interpreter; print('OK')"
   ```

   若报错 `No module named 'metagpt_attack_poc'`，说明当前工作目录或 `sys.path` 不对，请在第 2 步里从项目根目录运行脚本。

---

### 第 2 步：运行 PyRIT 场景

在 **项目根目录**（`memory_attack`）下执行，这样 `pyrit_memory_attack` 和 `Agent-Memory-Poisoning` 都在同一层级，路径才能被正确解析：

```bash
cd C:\Users\Lenovo\Desktop\memory_attack
python pyrit_memory_attack/run_metagpt_scenario.py
```

预期：

- **场景 1**：用示例攻击提示调用 MetaGPT DataInterpreter，并打印回复（前 500 字）。
- **场景 2**：依次运行 `exp3`、`exp4` 实验脚本，并打印输出（前 2000 字）。

若出现 `Abstract method ... not implemented` 等与 Target 相关的报错，说明你本地的 PyRIT 版本里 Target 接口可能不是 `send()`，请把完整报错贴出来，再根据接口改 `metagpt_target.py`。

---

### 第 3 步：改攻击提示或要跑的实验

- **改提示**：编辑 `pyrit_memory_attack/run_metagpt_scenario.py`，修改列表 `AGENT_ATTACK_PROMPTS`。
- **改实验**：修改同一文件中的 `EXPERIMENT_NAMES`，例如只跑 exp1、exp2：

  ```python
  EXPERIMENT_NAMES = ["exp1", "exp2"]
  ```

支持的实验名：`exp1` / `schema_spoof`、`exp2` / `judge_jack`、`exp3` / `memory_graft`、`exp4` / `rag_vector_drift`。

---

### 第 4 步：接入 Agent-Security 等其它 PyRIT 流程（可选）

若你希望用 Agent-Security 仓库里的 orchestrator / 数据集：

1. 把本目录下的 `metagpt_target.py` 复制到 Agent-Security 的 targets 目录（或按该项目的约定放置）。
2. 在 Agent-Security 的场景脚本里，将 **target** 设为 `MetaGPTAgentTarget()` 或 `MetaGPTExperimentTarget()`，其它流程（prompt 列表、scoring 等）按原项目来即可。
3. 运行场景时，确保当前工作目录或 `PYTHONPATH` 包含 `Agent-Memory-Poisoning`，以便 `metagpt_attack_poc` 能被导入（本目录的 `metagpt_target.py` 已自动把 `Agent-Memory-Poisoning` 加入 `sys.path`，只要目录结构如上所示即可）。

---

## 小结

| 步骤 | 操作 |
|------|------|
| 1 | 在 Agent-Memory-Poisoning 下执行 `pip install -e .`，并 `pip install pyrit` |
| 2 | 在 `memory_attack` 根目录执行：`python pyrit_memory_attack/run_metagpt_scenario.py` |
| 3 | 按需修改 `AGENT_ATTACK_PROMPTS` 和 `EXPERIMENT_NAMES` |
| 4 | 可选：把 `metagpt_target.py` 接入 Agent-Security 等 PyRIT 项目 |
