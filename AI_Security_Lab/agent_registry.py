"""
Agent 样本库（registry）解析与 HTTP Target 构造。

主线：`load_agents_registry` + `validate_agent_spec` + `build_http_target_from_spec`。
legacy：`build_target_from_spec` / inproc / subprocess 仍可用，但 **runner 默认只走 HTTP**，不加载 MetaAgent。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from http_target import HttpTarget

ProjectRoot = Path


class HealthcheckSpec(BaseModel):
    type: str = "http_get"
    path: str = "/"


class RuntimeSpec(BaseModel):
    deployment: str = "local_http"
    base_url: str = ""
    path: str = "/chat"
    method: str = "POST"
    input_key: str = "message"
    output_key: str = "output"
    timeout: float = 60.0
    healthcheck: HealthcheckSpec = Field(default_factory=HealthcheckSpec)


class HttpTargetConfig(BaseModel):
    """旧版 target.http 嵌套字段。"""

    base_url: str = ""
    path: str = "/chat"
    input_key: str = "message"
    output_key: str = "output"
    timeout: float = 60.0


class SubprocessTargetConfig(BaseModel):
    venv_python: str = ""
    entry_script: str = "subprocess_entry.py"


class AgentTargetSection(BaseModel):
    preferred_mode: Literal["auto", "http", "subprocess", "inproc"] = "auto"
    allow_fallback: bool = True
    allow_inproc_fallback: bool = True
    http: HttpTargetConfig | None = None
    subprocess: SubprocessTargetConfig = Field(default_factory=SubprocessTargetConfig)
    inproc: dict[str, Any] = Field(default_factory=dict)


class AgentSource(BaseModel):
    type: str = "local"
    repo_path: str = ""
    repo_url: str = ""


class EvaluationSpec(BaseModel):
    include_in_benchmark_summary: bool = True
    include_in_leaderboard: bool = True
    role: str = "benchmark"


class DefenseSpec(BaseModel):
    enabled: bool = False
    profile: str = "baseline"
    modules: list[str] = Field(default_factory=list)


class AgentSpec(BaseModel):
    id: str
    name: str = ""
    source: AgentSource
    runtime: RuntimeSpec | None = None
    target: AgentTargetSection | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)
    status: str = "candidate"
    tags: list[str] = Field(default_factory=list)
    evaluation: EvaluationSpec = Field(default_factory=EvaluationSpec)
    defense: DefenseSpec = Field(default_factory=DefenseSpec)
    notes: str = ""

    @model_validator(mode="after")
    def _migrate_legacy_target(self) -> AgentSpec:
        if self.runtime is not None:
            return self
        if self.target is None:
            self.runtime = RuntimeSpec()
            return self
        t = self.target
        h = t.http
        if h and h.base_url.strip():
            self.runtime = RuntimeSpec(
                deployment="local_http",
                base_url=h.base_url,
                path=h.path,
                method="POST",
                input_key=h.input_key,
                output_key=getattr(h, "output_key", None) or "output",
                timeout=float(h.timeout),
                healthcheck=HealthcheckSpec(type="http_get", path="/"),
            )
        else:
            self.runtime = RuntimeSpec(base_url="")
        return self


class AgentsRegistryFile(BaseModel):
    agents: list[AgentSpec]


@dataclass
class BuiltTarget:
    """备用：非 HTTP 路径或旧 batch 使用。"""

    target: Any
    run_param_name: str
    runtime_target: Literal["http", "subprocess", "inproc"]
    entry_file: str
    entry_name: str
    llm_suggested_target: str = ""
    llm_suggested_reason: str = ""


def load_agents_registry(path: str | Path) -> list[AgentSpec]:
    p = Path(path).resolve()
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not raw or "agents" not in raw:
        return []
    data = AgentsRegistryFile.model_validate(raw)
    return data.agents


def get_agent_tags(agent_spec: AgentSpec) -> list[str]:
    return list(agent_spec.tags or [])


def is_benchmark_target(agent_spec: AgentSpec) -> bool:
    ev = agent_spec.evaluation
    return bool(ev.include_in_benchmark_summary and ev.role == "benchmark")


def validate_agent_spec(agent_spec: AgentSpec, root: ProjectRoot) -> list[str]:
    errors: list[str] = []
    if not agent_spec.id.strip():
        errors.append("missing agent id")
    rt = agent_spec.runtime
    if rt is None:
        errors.append("missing runtime (and could not migrate from legacy target)")
        return errors
    if rt.deployment == "local_http":
        if not rt.base_url.strip():
            errors.append("local_http: base_url missing")
        if rt.method.upper() not in ("POST", "GET"):
            errors.append(f"unsupported HTTP method: {rt.method}")
    if agent_spec.source.type == "local" and not agent_spec.source.repo_path.strip():
        errors.append("local source missing repo_path")
    repo = (
        resolve_project_path(agent_spec.source.repo_path, root)
        if agent_spec.source.repo_path
        else None
    )
    if repo and not repo.is_dir():
        errors.append(f"repo_path not a directory: {repo}")
    return errors


def build_http_target_from_spec(agent_spec: AgentSpec) -> HttpTarget:
    rt = agent_spec.runtime
    if rt is None:
        raise ValueError("agent_spec.runtime missing")
    if rt.deployment != "local_http":
        raise ValueError(f"build_http_target_from_spec requires local_http, got {rt.deployment}")
    if not rt.base_url.strip():
        raise ValueError("HTTP base_url empty")
    return HttpTarget(
        base_url=rt.base_url,
        path=rt.path,
        method=rt.method,
        input_key=rt.input_key,
        output_key=rt.output_key,
        timeout=float(rt.timeout),
        health_path=rt.healthcheck.path,
        identifier=agent_spec.id,
    )


def resolve_project_path(path_str: str, root: ProjectRoot) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p.resolve()
    return (root / p).resolve()


def _pick_venv_python(repo_path: Path) -> Path | None:
    candidates = [
        repo_path / ".venv" / "Scripts" / "python.exe",
        repo_path / "venv" / "Scripts" / "python.exe",
        repo_path / ".venv" / "bin" / "python",
        repo_path / "venv" / "bin" / "python",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _resolve_venv_python(spec: AgentSpec, repo_path: Path, root: ProjectRoot) -> Path | None:
    t = spec.target
    if t is None:
        return _pick_venv_python(repo_path)
    s = t.subprocess.venv_python.strip()
    if s:
        vp = resolve_project_path(s, root)
        if vp.is_file():
            return vp
        rp = (repo_path / s).resolve()
        if rp.is_file():
            return rp
        return None
    return _pick_venv_python(repo_path)


def _http_config_ready_legacy(spec: AgentSpec) -> bool:
    t = spec.target
    if t is None:
        return False
    h = t.http
    return h is not None and bool(h.base_url.strip())


def _http_probe_legacy(spec: AgentSpec) -> bool:
    if not _http_config_ready_legacy(spec):
        return False
    t = spec.target
    assert t is not None
    h = t.http
    assert h is not None
    try:
        tgt = HttpTarget(
            base_url=h.base_url,
            path=h.path,
            input_key=h.input_key,
            output_key=getattr(h, "output_key", None) or "output",
            timeout=min(h.timeout, 15.0),
        )
        return tgt.healthcheck()
    except Exception:
        return False


def _subprocess_ready(spec: AgentSpec, repo_path: Path, root: ProjectRoot) -> bool:
    t = spec.target
    if t is None:
        return False
    script = repo_path / t.subprocess.entry_script
    venv = _resolve_venv_python(spec, repo_path, root)
    return bool(venv and venv.is_file() and script.is_file())


def resolve_runtime_target(agent_spec: AgentSpec, root: ProjectRoot) -> Literal["http", "subprocess", "inproc"]:
    """备用：旧 auto 模式解析。"""
    t = agent_spec.target
    if t is None:
        if agent_spec.runtime and agent_spec.runtime.deployment == "local_http":
            return "http"
        return "inproc"
    pref = t.preferred_mode
    if pref == "http":
        return "http"
    if pref == "subprocess":
        return "subprocess"
    if pref == "inproc":
        return "inproc"
    if _http_probe_legacy(agent_spec):
        return "http"
    repo = resolve_project_path(agent_spec.source.repo_path, root)
    if _subprocess_ready(agent_spec, repo, root):
        return "subprocess"
    return "inproc"


def _build_http_legacy(spec: AgentSpec, root: ProjectRoot) -> BuiltTarget:
    t = spec.target
    if t is None or t.http is None or not t.http.base_url.strip():
        raise ValueError("HTTP target config missing base_url")
    h = t.http
    tgt = HttpTarget(
        base_url=h.base_url,
        path=h.path,
        input_key=h.input_key,
        output_key=getattr(h, "output_key", None) or "output",
        timeout=h.timeout,
        identifier=spec.id,
    )
    return BuiltTarget(
        target=tgt,
        run_param_name=h.input_key,
        runtime_target="http",
        entry_file="",
        entry_name="",
    )


def _build_subprocess(spec: AgentSpec, root: ProjectRoot) -> BuiltTarget:
    from subprocess_target import SubprocessTarget

    t = spec.target
    if t is None:
        raise ValueError("legacy target missing for subprocess")
    repo_path = resolve_project_path(spec.source.repo_path, root)
    venv = _resolve_venv_python(spec, repo_path, root)
    if not venv or not venv.is_file():
        raise ValueError("subprocess: venv python not found")
    entry_script = t.subprocess.entry_script
    st = SubprocessTarget(
        repo_path=repo_path,
        venv_python=str(venv),
        entry_script=entry_script,
        identifier=spec.id,
    )
    return BuiltTarget(
        target=st,
        run_param_name="message",
        runtime_target="subprocess",
        entry_file=entry_script,
        entry_name="subprocess_entry",
    )


def _build_inproc(spec: AgentSpec, root: ProjectRoot) -> BuiltTarget:
    from meta_agent import MetaAgent

    repo_path = resolve_project_path(spec.source.repo_path, root)
    meta = MetaAgent(repo_path, model="deepseek-chat", max_snippet_lines=500)
    llm_suggested_target, llm_suggested_reason = "", ""
    try:
        diag = meta.diagnose_target_type()
        llm_suggested_target = diag.preferred_target
        llm_suggested_reason = diag.reason
    except Exception as e:
        llm_suggested_target = "unknown"
        llm_suggested_reason = f"diagnose_error: {type(e).__name__}: {e}"
    entry = meta.detect_entry()
    DynamicTarget = meta.build_dynamic_target_class(entry)
    inst = DynamicTarget()
    run_param_name = entry.params[0].name if entry.params else "message"
    return BuiltTarget(
        target=inst,
        run_param_name=run_param_name,
        runtime_target="inproc",
        entry_file=entry.entry_file,
        entry_name=entry.entry_name,
        llm_suggested_target=llm_suggested_target,
        llm_suggested_reason=llm_suggested_reason,
    )


def _try_build_mode(mode: Literal["http", "subprocess", "inproc"], spec: AgentSpec, root: ProjectRoot) -> BuiltTarget:
    if mode == "http":
        if spec.runtime and spec.runtime.deployment == "local_http":
            h = build_http_target_from_spec(spec)
            return BuiltTarget(
                target=h,
                run_param_name=spec.runtime.input_key,
                runtime_target="http",
                entry_file="",
                entry_name="",
            )
        return _build_http_legacy(spec, root)
    if mode == "subprocess":
        return _build_subprocess(spec, root)
    return _build_inproc(spec, root)


def _fallback_after_explicit(
    pref: Literal["http", "subprocess", "inproc"],
) -> list[Literal["http", "subprocess", "inproc"]]:
    if pref == "http":
        return ["subprocess", "inproc"]
    if pref == "subprocess":
        return ["inproc"]
    return []


def _strip_inproc_fallback_if_needed(
    order: list[Literal["http", "subprocess", "inproc"]],
    allow_inproc_fallback: bool,
) -> list[Literal["http", "subprocess", "inproc"]]:
    if allow_inproc_fallback:
        return order
    if not order:
        return order
    if order[0] == "inproc":
        return order
    return [m for m in order if m != "inproc"]


def build_target_from_spec(agent_spec: AgentSpec, root: ProjectRoot) -> BuiltTarget:
    """
    备用：多模式构造（HTTP / subprocess / inproc）。runner v1 请使用 build_http_target_from_spec。
    """
    t = agent_spec.target
    if t is None:
        if agent_spec.runtime and agent_spec.runtime.deployment == "local_http":
            h = build_http_target_from_spec(agent_spec)
            if not h.healthcheck():
                raise RuntimeError("healthcheck returned False")
            return BuiltTarget(
                target=h,
                run_param_name=agent_spec.runtime.input_key,
                runtime_target="http",
                entry_file="",
                entry_name="",
            )
        raise RuntimeError("build_target_from_spec: no legacy target and no local_http runtime")

    pref = t.preferred_mode
    allow = t.allow_fallback
    order: list[Literal["http", "subprocess", "inproc"]] = []

    if pref == "auto":
        primary = resolve_runtime_target(agent_spec, root)
        order.append(primary)
        if allow:
            for m in ("http", "subprocess", "inproc"):
                if m not in order:
                    order.append(m)
    else:
        order.append(pref)  # type: ignore[arg-type]
        if allow:
            for m in _fallback_after_explicit(pref):  # type: ignore[arg-type]
                if m not in order:
                    order.append(m)

    order = _strip_inproc_fallback_if_needed(order, t.allow_inproc_fallback)

    errors: list[str] = []
    for mode in order:
        try:
            built = _try_build_mode(mode, agent_spec, root)
            if not built.target.healthcheck():
                raise RuntimeError("healthcheck returned False")
            return built
        except Exception as e:
            errors.append(f"{mode}: {type(e).__name__}: {e}")

    raise RuntimeError("build_target_from_spec failed: " + " | ".join(errors))


def parse_legacy_repos_line(target_id: str) -> dict[str, Any]:
    raw = target_id.strip()
    lowered = raw.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return {"kind": "http", "base_url": raw, "raw": raw}

    if ":" in raw:
        prefix, rest = raw.split(":", 1)
        p = prefix.strip().lower()
        rest = rest.strip()
        if p == "http":
            if not rest:
                return {"kind": "http", "base_url": "", "raw": raw}
            return {"kind": "http", "base_url": rest, "raw": raw}
        if p == "inproc":
            return {"kind": "inproc", "repo_path": rest, "raw": raw}
        if p == "subprocess":
            parts = [x.strip() for x in rest.split("|")]
            repo_path = parts[0] if parts else ""
            venv_python = parts[1] if len(parts) >= 2 and parts[1] else ""
            entry_script = parts[2] if len(parts) >= 3 and parts[2] else "subprocess_entry.py"
            return {
                "kind": "subprocess",
                "repo_path": repo_path,
                "venv_python": venv_python,
                "entry_script": entry_script,
                "raw": raw,
            }

    return {"kind": "local", "repo_path": raw, "raw": raw}


def agent_spec_from_legacy_line(target_id: str, *, agent_id: str | None = None) -> AgentSpec:
    spec = parse_legacy_repos_line(target_id)
    raw = spec.get("raw", "legacy")
    lid = agent_id or (re.sub(r"[^a-zA-Z0-9_]+", "_", str(raw).strip()).strip("_")[:48] or "legacy")
    kind = spec.get("kind", "local")

    if kind == "http":
        base = spec.get("base_url") or ""
        return AgentSpec(
            id=lid,
            name=lid,
            source=AgentSource(type="local", repo_path=".", repo_url=""),
            target=AgentTargetSection(
                preferred_mode="http",
                allow_fallback=True,
                http=HttpTargetConfig(
                    base_url=base, path="/chat", input_key="message", output_key="output", timeout=60.0
                ),
            ),
        )

    repo_path = spec.get("repo_path") or ""
    if kind == "inproc":
        return AgentSpec(
            id=lid,
            name=lid,
            source=AgentSource(type="local", repo_path=repo_path, repo_url=""),
            target=AgentTargetSection(
                preferred_mode="inproc",
                allow_fallback=True,
            ),
        )

    if kind == "subprocess":
        return AgentSpec(
            id=lid,
            name=lid,
            source=AgentSource(type="local", repo_path=repo_path, repo_url=""),
            target=AgentTargetSection(
                preferred_mode="subprocess",
                allow_fallback=True,
                subprocess=SubprocessTargetConfig(
                    venv_python=spec.get("venv_python") or "",
                    entry_script=spec.get("entry_script") or "subprocess_entry.py",
                ),
            ),
        )

    return AgentSpec(
        id=lid,
        name=lid,
        source=AgentSource(type="local", repo_path=repo_path, repo_url=""),
        target=AgentTargetSection(preferred_mode="auto", allow_fallback=True),
    )
