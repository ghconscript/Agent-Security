"""
MetaAgent: 扫描本地仓库源码，通过 LLM 识别 Agent 入口并生成可执行的 DynamicTarget。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

# 可选：若使用 init_chat_model 需安装对应 provider（如 langchain-openai）
try:
    from langchain.chat_models import init_chat_model
except ImportError:
    init_chat_model = None


# ---------- LLM 返回的结构化结果 ----------


class ParamSpec(BaseModel):
    """单个参数的描述。"""

    name: str = Field(description="参数名")
    type_hint: str = Field(default="str", description="类型提示，如 str, int, list, dict")
    required: bool = Field(default=True, description="是否必填")
    description: str = Field(default="", description="参数说明")


class TopCandidateFiles(BaseModel):
    """Level 1：LLM 根据目录树选出的最像入口的 3 个文件（相对路径）。"""

    candidate_files: list[str] = Field(
        description="最可能是 Agent/程序入口的 3 个 Python 文件路径，相对于仓库根目录，如 ['src/main.py', 'agent/runner.py']",
        min_length=1,
        max_length=5,
    )


class AgentEntryResult(BaseModel):
    """LLM 返回的 Agent 入口信息。"""

    entry_file: str = Field(description="入口所在文件路径，相对于仓库根目录")
    entry_line: int = Field(description="入口定义所在行号（1-based）")
    entry_name: str = Field(description="入口名称：函数名或 类名.方法名，如 'main' 或 'Agent.run'")
    params: list[ParamSpec] = Field(default_factory=list, description="调用该入口所需的参数列表")
    is_method: bool = Field(
        default=False,
        description="入口是否为类方法（True 则 entry_name 格式为 ClassName.method_name）"
    )
    reason: str = Field(
        default="",
        description="判定该文件/位置为入口的理由，便于人工核对是否真的理解了代码逻辑",
    )


class TargetDiagnosis(BaseModel):
    """LLM 辅助诊断：适合的 Target 类型及理由。"""

    preferred_target: Literal["inproc", "subprocess", "http", "unknown"] = Field(
        description="推荐的 Target 类型：inproc / subprocess / http / unknown",
    )
    reason: str = Field(
        default="",
        description="为什么推荐该 Target 类型的理由，基于 README / 依赖 / 代码结构等。",
    )


# ---------- 关键行匹配 ----------

KEY_PATTERNS = ("def ", "class ", "run", "chat")
KEY_PATTERNS_RE = re.compile(
    "|".join(re.escape(p) for p in KEY_PATTERNS),
    re.IGNORECASE,
)


def _is_key_line(line: str) -> bool:
    """判断是否为关键代码行（包含 def/class/run/chat）。"""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    return bool(KEY_PATTERNS_RE.search(stripped))


def _collect_snippets_from_file(file_path: str, root: str) -> list[tuple[int, str]]:
    """从单个文件中收集关键行及其行号（1-based）。"""
    snippets: list[tuple[int, str]] = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, start=1):
                if _is_key_line(line):
                    snippets.append((i, line.rstrip()))
    except OSError:
        pass
    return snippets


def _collect_snippets_with_context(
    file_path: str,
    root: str,
    context_before: int = 2,
    context_after: int = 10,
) -> list[tuple[int, list[str]]]:
    """
    深度切片：收集 def/class 等关键行及其前后上下文，返回 [(起始行号, 行列表), ...]。
    用于 Level 2 只读候选文件时，让 LLM 看到函数/类体而非单行。
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip() for ln in f]
    except OSError:
        return []
    n = len(lines)
    blocks: list[tuple[int, list[str]]] = []
    seen_starts: set[int] = set()
    for i in range(n):
        if not _is_key_line(lines[i]):
            continue
        start = max(0, i - context_before)
        end = min(n, i + context_after + 1)
        if start in seen_starts:
            continue
        seen_starts.add(start)
        block_lines = lines[start:end]
        start_line_1based = start + 1
        blocks.append((start_line_1based, block_lines))
    return blocks


def _normalize_path(path: str, root: str) -> str:
    """将绝对路径转为相对于 root 的路径，使用 / 分隔。"""
    try:
        return os.path.relpath(path, root).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


# ---------- MetaAgent ----------


class MetaAgent:
    """
    接受本地仓库路径，扫描 Python 文件中的关键片段，交给 LLM 识别 Agent 入口，
    并生成 DynamicTarget 用于动态导入与执行。
    """

    def __init__(
        self,
        repo_path: str | Path,
        *,
        llm: Any | None = None,
        model: str = "deepseek-chat",  # DeepSeek；部署时可用环境变量 DEEPSEEK_API_KEY
        api_key: str | None = None,  # 部署时用环境变量 DEEPSEEK_API_KEY，或调用时传入 api_key="sk-..."
        llm_kwargs: dict[str, Any] | None = None,
        exclude_dirs: tuple[str, ...] = (".git", "__pycache__", ".venv", "venv", "node_modules", ".tox", "dist", "build"),
        max_snippet_lines: int = 500,
        context_before: int = 2,
        context_after: int = 10,
    ):
        """
        Args:
            repo_path: 本地仓库（或任意 Python 项目）根目录路径。
            llm: 已配置的 LangChain ChatModel；若为 None 则使用 init_chat_model(model=model, ...)。
            model: 当 llm 为 None 时用于初始化聊天模型的模型名。
            api_key: LLM API Key。若不传则从环境变量读取（DeepSeek 用 DEEPSEEK_API_KEY，OpenAI 用 OPENAI_API_KEY）。部署时建议在环境/配置中设置，勿写死在代码里。
            llm_kwargs: 创建 LLM 时传给 init_chat_model 的额外参数（如 temperature、base_url 等）。
            exclude_dirs: 遍历时跳过的目录名。
            max_snippet_lines: 发送给 LLM 的代码总行数上限（避免超长上下文）。
            context_before: Level 2 深度切片时，def/class 行前保留的行数。
            context_after: Level 2 深度切片时，def/class 行后保留的行数。
        """
        self.repo_path = Path(repo_path).resolve()
        if not self.repo_path.is_dir():
            raise NotADirectoryError(f"repo_path 必须是目录: {self.repo_path}")

        self.exclude_dirs = set(exclude_dirs)
        self.max_snippet_lines = max_snippet_lines
        self.context_before = context_before
        self.context_after = context_after

        if llm is not None:
            self.llm = llm
        elif init_chat_model is not None:
            kwargs: dict[str, Any] = dict(llm_kwargs or {})
            key = api_key or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
            if key:
                kwargs["api_key"] = key
            self.llm = init_chat_model(model=model, **kwargs)
        else:
            raise RuntimeError(
                "请传入 llm 或安装 langchain 及对应 provider（如 pip install langchain langchain-openai）"
            )

        self._entry_result: AgentEntryResult | None = None

    def _walk_python_files(self):
        """使用 os.walk 遍历仓库下所有 .py 文件（跳过 exclude_dirs）。"""
        for dirpath, dirnames, filenames in os.walk(self.repo_path, topdown=True):
            dirnames[:] = [d for d in dirnames if d not in self.exclude_dirs]
            for name in filenames:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)

    def _build_directory_tree(self) -> str:
        """Level 1：仅目录树，所有 .py 文件的相对路径，每行一个。"""
        lines = []
        for file_path in self._walk_python_files():
            rel = _normalize_path(file_path, str(self.repo_path))
            lines.append(rel)
        return "\n".join(lines) if lines else "(无 Python 文件)"

    def _build_snippets_payload(self, file_paths: list[str] | None = None) -> str:
        """
        收集关键代码片段。若指定 file_paths（相对路径列表），则只处理这些文件；
        否则处理所有 .py 文件。
        """
        root = str(self.repo_path)
        if file_paths is not None:
            iter_files = []
            for p in file_paths:
                norm = p.strip().replace("\\", "/")
                abs_path = (self.repo_path / norm).resolve()
                if abs_path.is_file():
                    iter_files.append(str(abs_path))
        else:
            iter_files = list(self._walk_python_files())

        lines_used = 0
        parts: list[str] = []

        use_deep_slice = file_paths is not None

        for fp in iter_files:
            if lines_used >= self.max_snippet_lines:
                break
            rel = _normalize_path(fp, root)
            if use_deep_slice:
                snippet_blocks = _collect_snippets_with_context(
                    fp, root,
                    context_before=getattr(self, "context_before", 2),
                    context_after=getattr(self, "context_after", 10),
                )
                for start_line, block_lines in snippet_blocks:
                    if lines_used >= self.max_snippet_lines:
                        break
                    block: list[str] = [f"# file: {rel}"]
                    for j, line in enumerate(block_lines):
                        if lines_used >= self.max_snippet_lines:
                            break
                        block.append(f"  {start_line + j}: {line}")
                        lines_used += 1
                    if len(block) > 1:
                        parts.append("\n".join(block))
            else:
                snippets = _collect_snippets_from_file(fp, root)
                if not snippets:
                    continue
                block = [f"# file: {rel}"]
                for line_no, line in snippets:
                    if lines_used >= self.max_snippet_lines:
                        break
                    block.append(f"  {line_no}: {line}")
                    lines_used += 1
                if len(block) > 1:
                    parts.append("\n".join(block))

        return "\n\n".join(parts) if parts else "(未找到包含 def/class/run/chat 的代码行)"

    def diagnose_target_type(self) -> TargetDiagnosis:
        """
        使用 LLM 结合 README / 依赖信息，辅助诊断更适合的 Target 类型。

        仅做建议，不作为硬判定；返回 preferred_target 和理由，供前端展示或人工复核。
        """
        readme_text = ""
        for name in ("README.md", "README.MD", "readme.md"):
            p = self.repo_path / name
            if p.is_file():
                try:
                    readme_text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    readme_text = ""
                break

        pyproject_text = ""
        pyproject_path = self.repo_path / "pyproject.toml"
        if pyproject_path.is_file():
            try:
                pyproject_text = pyproject_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pyproject_text = ""

        req_text = ""
        for name in ("requirements.txt", "requirements-dev.txt", "requirements.in"):
            p = self.repo_path / name
            if p.is_file():
                try:
                    req_text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    req_text = ""
                break

        context_parts: list[str] = []
        if readme_text:
            context_parts.append("README.md:\n" + readme_text[:4000])
        if pyproject_text:
            context_parts.append("pyproject.toml:\n" + pyproject_text[:3000])
        if req_text:
            context_parts.append("requirements:\n" + req_text[:3000])

        context = "\n\n".join(context_parts) or "(无 README / 依赖信息)"

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """你是一个代码分析助手，帮助决定如何在攻击/防御测试平台中运行一个 Agent 仓库。

请根据提供的 README / 依赖信息，判断更推荐哪种运行方式：
- "inproc": 直接在当前 Python 进程 import 并调用（依赖较新、与当前环境兼容概率高）；
- "subprocess": 在独立虚拟环境中以子进程运行（依赖老旧、需要特定版本或重依赖）；
- "http": 仓库更像是一个 Web 服务 / API（FastAPI/Flask/uvicorn/gunicorn/Docker），适合作为 HTTP Target。

仅从 README / 依赖和明显信号出发做一个建议，不需要 100% 准确。
""",
                ),
                (
                    "human",
                    "下面是该仓库的 README / 依赖等信息，请给出推荐的 Target 类型，并解释理由：\n\n{context}",
                ),
            ]
        )

        structured_llm = self.llm.with_structured_output(TargetDiagnosis)
        chain = prompt | structured_llm
        result = chain.invoke({"context": context})

        if isinstance(result, dict):
            return TargetDiagnosis(**result)
        if isinstance(result, TargetDiagnosis):
            return result
        return TargetDiagnosis(**result.model_dump())

    def _detect_entry_level1(self) -> list[str]:
        """Level 1：只发目录树，让 LLM 选出最像入口的 3 个文件。"""
        tree_text = self._build_directory_tree()
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个代码分析助手。根据用户提供的 Python 仓库「文件目录树」（仅文件名列表），选出最可能是 Agent/程序入口的 3 个文件。
重点关注：main、run、app、agent、client、bridge 等命名；入口常出现在根目录或 src、app、agent 等子目录。"""),
            ("human", "请从以下目录树中选出最像入口的 3 个文件，只返回这 3 个文件的相对路径。\n\n{tree}"),
        ])
        structured_llm = self.llm.with_structured_output(TopCandidateFiles)
        chain = prompt | structured_llm
        result = chain.invoke({"tree": tree_text})
        if isinstance(result, dict):
            result = TopCandidateFiles(**result)
        elif not isinstance(result, TopCandidateFiles):
            result = TopCandidateFiles(**result.model_dump())
        return result.candidate_files[:3]

    def detect_entry(self) -> AgentEntryResult:
        """
        多级扫描：Level 1 只看目录树选 3 个候选文件，Level 2 只读这 3 个文件的代码片段做精确识别。
        结果会缓存在 self._entry_result，并用于生成 DynamicTarget。
        """
        # Level 1：目录树 → 选出 3 个候选文件
        candidate_files = self._detect_entry_level1()
        if not candidate_files:
            candidate_files = [
                _normalize_path(p, str(self.repo_path)).replace("\\", "/")
                for p in self._walk_python_files()
            ][:3]

        # Level 2：只读候选文件的代码片段，精确识别入口
        snippets_text = self._build_snippets_payload(candidate_files)

        system_msg = """你是一个代码分析助手。根据用户提供的 Python 仓库代码片段，找出「Agent 的入口」。
入口通常是：main、run、chat、invoke、execute 等函数，或某个 Agent 类的 run/chat/invoke 方法。
请只返回一个最可能的入口。若无法确定，则选择最像「主入口」的函数或方法。
针对爬虫/自动化项目：重点关注带有 Client, Agent, main, bridge 关键词的类，以及使用了 requests 或 playwright 的异步函数。
必须填写 reason 字段：用一两句话说明你判定该位置为入口的理由（例如依据了哪些函数名、类名或调用关系），便于人工核对是否真的理解了代码逻辑。"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("human", "请根据以下代码片段，判断该仓库中 Agent 的入口位置与调用方式。\n\n{code}"),
        ])

        structured_llm = self.llm.with_structured_output(AgentEntryResult)
        chain = prompt | structured_llm
        result = chain.invoke({"code": snippets_text})

        if isinstance(result, dict):
            result = AgentEntryResult(**result)
        elif not isinstance(result, AgentEntryResult):
            result = AgentEntryResult(**result.model_dump())

        self._entry_result = result
        return result

    def get_entry_result(self) -> AgentEntryResult | None:
        """返回最近一次 detect_entry 的结果；若未调用过则为 None。"""
        return self._entry_result

    def build_dynamic_target_class(self, entry_result: AgentEntryResult | None = None) -> type:
        """
        根据入口信息生成并返回 DynamicTarget 类。
        若未传入 entry_result，则使用上次 detect_entry 的结果。
        """
        er = entry_result or self._entry_result
        if er is None:
            raise ValueError("请先调用 detect_entry() 或传入 entry_result")

        entry_file_abs = self.repo_path / er.entry_file.replace("/", os.sep)
        if not entry_file_abs.is_file():
            raise FileNotFoundError(f"入口文件不存在: {entry_file_abs}")

        entry_name = er.entry_name
        is_method = er.is_method
        params_specs = er.params

        class DynamicTarget:
            """
            动态加载指定文件并执行入口函数/方法的封装类。
            通过 run(**kwargs) 传入参数并执行。
            """

            _repo_path: Path = self.repo_path
            _entry_file: Path = entry_file_abs
            _entry_name: str = entry_name
            _is_method: bool = is_method
            _params_specs: list[ParamSpec] = params_specs

            def __init__(self, repo_path: Path | None = None):
                if repo_path is not None:
                    self._repo_path = Path(repo_path)
                    self._entry_file = self._repo_path / er.entry_file.replace("/", os.sep)

            @classmethod
            def get_params_schema(cls) -> list[dict[str, Any]]:
                """返回调用入口所需的参数 schema（便于 UI/API 生成表单）。"""
                return [
                    {
                        "name": p.name,
                        "type": p.type_hint,
                        "required": p.required,
                        "description": p.description,
                    }
                    for p in cls._params_specs
                ]

            def _load_module(self):
                """将入口文件作为模块加载（支持任意路径，不要求包结构）。"""
                spec = importlib.util.spec_from_file_location(
                    "dynamic_agent_module",
                    self._entry_file,
                    submodule_search_locations=[str(self._repo_path)],
                )
                if spec is None or spec.loader is None:
                    raise ImportError(f"无法加载模块: {self._entry_file}")
                module = importlib.util.module_from_spec(spec)
                if str(self._repo_path) not in sys.path:
                    sys.path.insert(0, str(self._repo_path))
                spec.loader.exec_module(module)
                return module

            def run(self, **kwargs) -> Any:
                """
                动态 import 入口文件并执行入口函数/方法。
                kwargs 应与 get_params_schema() 中的参数对应。
                """
                module = self._load_module()

                if self._is_method:
                    part = self._entry_name.split(".", 1)
                    if len(part) != 2:
                        raise ValueError(f"方法入口格式应为 'ClassName.method_name': {self._entry_name}")
                    class_name, method_name = part
                    cls = getattr(module, class_name, None)
                    if cls is None:
                        raise AttributeError(f"模块中未找到类: {class_name}")
                    try:
                        obj = cls()
                    except TypeError:
                        obj = cls
                    method = getattr(obj, method_name, None)
                    if method is None:
                        raise AttributeError(f"类 {class_name} 中未找到方法: {method_name}")
                    return method(**kwargs)
                else:
                    func = getattr(module, self._entry_name, None)
                    if func is None:
                        raise AttributeError(f"模块中未找到函数: {self._entry_name}")
                    return func(**kwargs)

            def healthcheck(self) -> bool:
                try:
                    self._load_module()
                    return True
                except Exception:
                    return False

            def describe(self) -> dict[str, Any]:
                run_param = (
                    self._params_specs[0].name if self._params_specs else "message"
                )
                rel_entry = _normalize_path(str(self._entry_file), str(self._repo_path))
                return {
                    "target_kind": "inproc",
                    "identifier": str(self._repo_path),
                    "entry_file": rel_entry.replace("\\", "/"),
                    "entry_name": self._entry_name,
                    "run_param_name": run_param,
                }

        return DynamicTarget


# ---------- 便捷函数 ----------


def run_agent_from_repo(
    repo_path: str | Path,
    *,
    llm: Any | None = None,
    model: str = "deepseek-chat",
    api_key: str | None = None,
    llm_kwargs: dict[str, Any] | None = None,
    **run_kwargs: Any,
) -> Any:
    """
    一键：扫描仓库 → 检测入口 → 构建 DynamicTarget → 执行 run(**run_kwargs)。
    适合入口参数已知、且已配置好 LLM 的快速测试。
    """
    meta = MetaAgent(
        repo_path,
        llm=llm,
        model=model,
        api_key=api_key,
        llm_kwargs=llm_kwargs,
    )
    meta.detect_entry()
    target_class = meta.build_dynamic_target_class()
    target = target_class()
    return target.run(**run_kwargs)
