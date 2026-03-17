## Agent Memory Attack 使用说明

本文件夹 `memory_attack` 是你在本机上用来复现与扩展 **智能体记忆 / 检索投毒攻击** 的工作目录，主要基于：

- **MetaGPT / Agent-Memory-Poisoning**：提供多智能体环境和 4 个记忆投毒实验脚本。
- **LLM 接入配置**：已支持 DeepSeek、文心一言（千帆 Qianfan）等 OpenAI 兼容或专用接口。
- **PyRIT 集成（pyrit_memory_attack）**：用于在红队框架下统一驱动 Agent 与实验脚本。

可以把这里理解为：**一个专门用于研究“如何攻击智能体记忆与检索”的本地实验平台**。

---

## 一、目录总览

当前目录结构（只列与实验相关的部分）：

```text
memory_attack/
├── Agent-Memory-Poisoning/        # 上游项目：MetaGPT + 记忆投毒 PoC
│   ├── config/
│   │   └── config2.yaml           # LLM / Embedding 配置（已改为 DeepSeek / Qianfan 等）
│   └── metagpt_attack_poc/
│       ├── experiments/
│       │   ├── exp1_schema_spoof.py       # 实验 1：Schema-Spoofing（文档/Schema 伪造）
│       │   ├── exp2_judge_jack.py         # 实验 2：JudgeJacking（校验作弊）
│       │   ├── exp3_memory_graft.py       # 实验 3：Memory Graft（经验池投毒）
│       │   └── exp4_rag_vector_drift.py   # 实验 4：RAG 向量漂移投毒
│       ├── payloads/                      # 投毒用的种子数据（经验 JSON、带毒笔记等）
│       └── pyrit_entrypoints.py           # 对外暴露给 PyRIT 的统一入口函数
└── pyrit_memory_attack/
    ├── metagpt_target.py          # 自定义 Target：封装 DataInterpreter 与实验脚本
    ├── run_metagpt_scenario.py    # 场景脚本：一次性运行提示攻击 + 实验 3/4
    ├── README.md                  # 针对 pyrit_memory_attack 子目录的详细说明
    └── ...（后续可以放更多 PyRIT 场景）
```

> 额外说明：`C:\Users\Lenovo\.metagpt\config2.yaml` 中也已经同步成 DeepSeek / 文心一言 的全局配置，避免被旧配置覆盖。

---

## 二、环境配置与前置条件

### 1. Python 环境

- 当前实验在 **Windows + Python 3.10.11** 环境下完成。
- 建议使用虚拟环境（venv/conda），避免与其他项目依赖冲突。

### 2. 安装代码依赖

在 PowerShell 中依次执行（已完成，可用于重新搭环境时参考）：

```powershell
cd C:\Users\Lenovo\Desktop\memory_attack\Agent-Memory-Poisoning

# 以可编辑模式安装本地 MetaGPT/攻击代码
python -m pip install -e .

# 可选：如需使用完整 PyRIT 功能（不只是 demo 场景），安装：
python -m pip install pyrit
```

> 安装过程中遇到的部分依赖冲突，已通过固定版本与关闭某些不用的 provider（如 spark、volcengine ark）规避，不影响当前四个实验与 PyRIT 场景运行。

### 3. LLM 与 API Key 配置

当前主要支持两种 LLM 接法：

1. **DeepSeek（推荐）**

   - `Agent-Memory-Poisoning/config/config2.yaml` 中：

     ```yaml
     llm:
       api_type: "openai"
       model: "deepseek-chat"   # 或 deepseek-reasoner
       base_url: "https://api.deepseek.com/v1"
       api_key: "${OPENAI_API_KEY}"

     embedding:
       api_type: "openai"
       base_url: "https://api.deepseek.com/v1"
       api_key: "${OPENAI_API_KEY}"
       model: ""
       dimensions: 1536
     ```

   - 根目录 `.env` 中：

     ```env
     OPENAI_API_KEY=你的_DeepSeek_API_Key
     ```

2. **文心一言 / 千帆 Qianfan（可切换）**

   - `config2.yaml` 中：

     ```yaml
     llm:
       api_type: "qianfan"
       model: "ERNIE-Bot-4"
       access_key: "${QIANFAN_ACCESS_KEY}"
       secret_key: "${QIANFAN_SECRET_KEY}"
       base_url: ""
     ```

   - `.env` 中：

     ```env
     QIANFAN_ACCESS_KEY=你的AK
     QIANFAN_SECRET_KEY=你的SK
     ```

> RAG / 经验池相关实验目前统一采用 **BM25 检索**，不强制依赖 embedding API，从而规避 onnxruntime 在 Windows 上的 DLL 问题。

---

## 三、四个攻击实验的使用方法（单独运行）

以下命令均在 `Agent-Memory-Poisoning` 子目录下执行：

```powershell
cd C:\Users\Lenovo\Desktop\memory_attack\Agent-Memory-Poisoning
```

### 实验 1：Schema-Spoofing（文档/Schema 伪造）

- 脚本：`metagpt_attack_poc/experiments/exp1_schema_spoof.py`
- 思路：在 README 等文档中注入伪造的 “Code executed: ...”、“bootstrap.internal” 等执行痕迹，使 Agent 在阅读文档之后，相信某些危险操作已经被“安全执行过”，从而在新任务中模仿这些模式。

运行：

```powershell
python metagpt_attack_poc/experiments/exp1_schema_spoof.py
```

---

### 实验 2：JudgeJacking（校验作弊）

- 脚本：`metagpt_attack_poc/experiments/exp2_judge_jack.py`
- 思路：放置一个 `task_script.py`，输出格式正确但语义是假的“全部通过”（如 “106 passed”“ALL CHECKS PASSED”），欺骗 Agent 的成功判定逻辑，使其误以为测试/校验真正通过。

运行：

```powershell
python metagpt_attack_poc/experiments/exp2_judge_jack.py
```

---

### 实验 3：Memory Graft（经验池投毒）

- 脚本：`metagpt_attack_poc/experiments/exp3_memory_graft.py`
- 思路：往经验池写入 100 条良性经验 + 10 条恶意经验（比如跳过数据质量检查、使用远程 `curl | bash` 等），后续 Agent 在执行任务时，语义检索会优先召回这些“带毒成功经验”。
- 当前配置：使用 **BM25 检索**，无需 embedding。

运行：

```powershell
python metagpt_attack_poc/experiments/exp3_memory_graft.py
```

---

### 实验 4：RAG 向量漂移投毒（RAG Vector-Drift）

- 脚本：`metagpt_attack_poc/experiments/exp4_rag_vector_drift.py`
- 思路：使用与实验 3 同一批良性/投毒经验构建 RAG 索引，然后用一批“看似正常”的查询（如“快速清洗 PII 列”“跳过 schema 校验但保持流水线为绿”等）测试检索结果中投毒内容的比例（PRR）。
- 当前版本：同样采用 BM25-only 索引，避免 embedding 兼容问题。

运行：

```powershell
python metagpt_attack_poc/experiments/exp4_rag_vector_drift.py
```

---

## 四、PyRIT 集成场景（统一入口）

为了在红队评估框架下统一驱动 Agent 与实验，本目录下新增了 `pyrit_memory_attack` 子目录，提供两个关键文件：

1. **`metagpt_target.py`**

   - `MetaGPTAgentTarget`：封装 MetaGPT 的 `DataInterpreter`，暴露 `async send(prompt) -> str` 接口。
   - `MetaGPTExperimentTarget`：封装四个实验脚本，通过 `send("exp3")` 等方式触发对应实验。
   - 若环境中存在 `pyrit.targets.base_target.Target`，会自动继承以便接入 PyRIT；否则仅继承 `object`，但接口保持一致。

2. **`run_metagpt_scenario.py`**

   - 场景 1：对 `DataInterpreter` 做一次“绕过数据质量校验”的提示攻击。
   - 场景 2：通过 `MetaGPTExperimentTarget` 依次运行实验 3 和 4，并输出关键结果。

运行方法（在 `memory_attack` 根目录）：

```powershell
cd C:\Users\Lenovo\Desktop\memory_attack
python pyrit_memory_attack/run_metagpt_scenario.py
```

> 该脚本目前主要作为“整合 demo”：证明在一个统一入口下，可以同时驱动 **提示注入攻击** 与 **记忆/RAG 投毒实验**。

---

## 五、目前已实现的效果（简要总结）

1. **LLM 完整替换为 DeepSeek / 文心一言**  
   - 通过 `config2.yaml` 与 `.env`，将 MetaGPT 中所有原始 OpenAI 调用改为 DeepSeek（兼容接口）或 Qianfan。
   - 解决了在中国大陆地区无法直连 OpenAI 接口的问题。

2. **Windows 环境兼容性修复**  
   - 针对 GBK 编码导致的 `UnicodeDecodeError` / `UnicodeEncodeError`，统一在文件读写中显式使用 `encoding='utf-8'`，并替换脚本中的 emoji 为 ASCII 文本。  
   - 对 onnxruntime / chromadb 相关的错误，通过 **延迟导入** 与默认使用 BM25 检索绕过。

3. **四个实验全部在本机跑通**  
   - 实验 1–4 在当前配置下均能完整执行，且攻击效果可观（例如 RAG 实验中，在 9.1% 投毒比例下 PRR 可达 40% 以上）。

4. **与 PyRIT 的基础集成已完成**  
   - 已经可以通过 `run_metagpt_scenario.py` 一次性执行提示攻击 + 记忆投毒，并为后续接入 Agent-Security 等框架打下基础。

---

## 六、接下来可改进的方向

1. **接入正式的 PyRIT orchestrator 与 scoring**
   - 当前 `run_metagpt_scenario.py` 仅使用自写的简单循环逻辑；下一步可以：
     - 使用 PyRIT 提供的 `PromptSendingOrchestrator`、`RedTeamingOrchestrator` 等，对 `MetaGPTAgentTarget` 做多轮提示攻击。
     - 引入 scoring 组件（关键字/正则/LLM 评判）来自动判定攻击是否成功，统计成功率曲线。

2. **扩展攻击话术与任务类型**
   - 为 DataInterpreter 设计多种角色设定与攻击目标（例如绕过权限审核、隐私保护、合规校验等），构成系统化的 prompt 集合。
   - 在 PyRIT 中加载这些 prompt，进行批量评估。

3. **增加更多“记忆投毒”变体**
   - 在现有 Memory Graft / RAG 向量漂移基础上，尝试：
     - 以不同比例/不同语义区域注入投毒经验，研究 PRR 与投毒占比的关系。
     - 注入反向投毒（看似安全但实际降低模型对风险的敏感度）。

4. **自动化报告生成**
   - 对每次实验的关键指标（例如 PRR、毒检索条数、Agent 是否给出具体攻击代码等）自动汇总为 JSON/Markdown 报告，方便老师审阅与论文整理。

5. **支持更多 LLM 提供商**
   - 在保持 DeepSeek / Qianfan 配置的前提下，增加对其他国内外 LLM（如智谱、通义等）的配置模板，做跨模型对比实验。

---

总体来说，这个 `memory_attack` 目录已经完成了：

- **从 LLM 配置 → 智能体行为 → 记忆/RAG 层结构** 的端到端投毒实验搭建；
- 并初步与 PyRIT 框架打通，为后续系统化红队与研究留出扩展空间。

后续可以在此基础上，进一步增加自动化评估、更多攻击类型与防御策略，对比不同模型/配置下的安全性差异。+

# Agent_Memory_Attack
