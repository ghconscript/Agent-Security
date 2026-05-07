# ============================================================
# 防御引擎 — FastAPI 后端服务
#
# 启动: uvicorn server:app --host 0.0.0.0 --port 8100
# 文档: http://localhost:8100/docs (Swagger)
# ============================================================

import json
import time
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from .defense_types import (
        DefenseLayer, DefenseContext, DefenseMode,
        LayerCheckResult, DefenseTestResult,
    )
    from .rule_engine import RuleEngine
    from .orchestrator import DefenseOrchestrator
except ImportError:
    from defense_types import (
        DefenseLayer, DefenseContext, DefenseMode,
        LayerCheckResult, DefenseTestResult,
    )
    from rule_engine import RuleEngine
    from orchestrator import DefenseOrchestrator

# ---- 初始化 ----

app = FastAPI(
    title="LLM Agent 防御引擎",
    description="五层纵深防御体系 API — 评测平台后端",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 加载预设规则
ROOT = Path(__file__).parent
RULES_PATH = ROOT / "config" / "defense_rules.json"


def _load_rules() -> list[dict]:
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [r for r in data["rules"] if "rule_id" in r and not r.get("_comment")]


def _build_layer_config(layer: DefenseLayer, rules: list[dict],
                        enabled: bool, description: str,
                        params: dict) -> dict:
    """构造单层配置响应"""
    layer_rules = [r for r in rules if r["rule_id"].startswith(_layer_prefix(layer))]
    return {
        "layer": layer.value,
        "label": _LAYER_LABELS[layer],
        "enabled": enabled,
        "description": description,
        "rules": layer_rules,
        "params": params,
        "stats": {
            "total_checks": 0,
            "total_blocked": 0,
            "block_rate": 0.0,
        },
    }


_LAYER_LABELS = {
    DefenseLayer.SOURCE_GOVERNANCE: "源头数据与供应链治理",
    DefenseLayer.MODEL_INTERACTION: "模型交互与上下文约束",
    DefenseLayer.MEMORY_CONTROL: "记忆读写安全控制",
    DefenseLayer.TOOL_CONSTRAINT: "工具调用与执行安全控制",
    DefenseLayer.DECISION_SUPERVISION: "决策监督与多源验证",
}

_LAYER_PREFIX = {
    DefenseLayer.SOURCE_GOVERNANCE: "SG",
    DefenseLayer.MODEL_INTERACTION: "MI",
    DefenseLayer.MEMORY_CONTROL: "MC",
    DefenseLayer.TOOL_CONSTRAINT: "TC",
    DefenseLayer.DECISION_SUPERVISION: "DS",
}


def _layer_prefix(layer: DefenseLayer) -> str:
    return _LAYER_PREFIX.get(layer, "")


# 引擎实例 (从预设规则初始化)
_preset_rules = _load_rules()
_engine = RuleEngine(_preset_rules)
_orchestrator = DefenseOrchestrator(_engine, mode=DefenseMode.BALANCED)

# 当前层启用状态
_enabled_layers: dict[str, bool] = {
    layer.value: True for layer in DefenseLayer
}

# 同步 _enabled_layers 到 orchestrator
def _sync_orch_layers():
    for layer in DefenseLayer:
        _orchestrator.set_layer_enabled(layer, _enabled_layers.get(layer.value, True))

_sync_orch_layers()

# 统计计数器
_stats: dict[str, dict] = {
    layer.value: {"checks": 0, "blocked": 0}
    for layer in DefenseLayer
}


# ---- API 端点 ----

# 1. GET /api/defenses/layers
@app.get("/api/defenses/layers")
async def get_layers():
    """获取五层防御架构定义 (含规则和当前启用状态)"""
    rules = _engine.get_all_rules()

    return {
        "code": 200,
        "message": "ok",
        "data": [
            _build_layer_config(
                DefenseLayer.SOURCE_GOVERNANCE, rules,
                _enabled_layers[DefenseLayer.SOURCE_GOVERNANCE.value],
                "在Agent接触内容之前，对外部文件、RAG文档、API返回值等进行安全处理",
                {"source_whitelist": ["internal_db", "verified_api"], "max_file_size_mb": 50},
            ),
            _build_layer_config(
                DefenseLayer.MODEL_INTERACTION, rules,
                _enabled_layers[DefenseLayer.MODEL_INTERACTION.value],
                "覆盖Agent接收请求、组织上下文和生成输出的过程",
                {"context_separation": True, "max_context_tokens": 16000},
            ),
            _build_layer_config(
                DefenseLayer.MEMORY_CONTROL, rules,
                _enabled_layers[DefenseLayer.MEMORY_CONTROL.value],
                "对记忆的读取、写入、更新和删除进行全过程控制",
                {"default_ttl_hours": 24, "max_memory_entries": 1000},
            ),
            _build_layer_config(
                DefenseLayer.TOOL_CONSTRAINT, rules,
                _enabled_layers[DefenseLayer.TOOL_CONSTRAINT.value],
                "约束Agent调用外部工具、API或执行动作前后的安全边界",
                {"high_risk_actions": ["file_write", "network_request", "system_command"]},
            ),
            _build_layer_config(
                DefenseLayer.DECISION_SUPERVISION, rules,
                _enabled_layers[DefenseLayer.DECISION_SUPERVISION.value],
                "在最终输出或关键动作执行前进行复核",
                {"audit_threshold": 0.7, "vote_threshold": 0.6},
            ),
        ],
    }


# 2. GET /api/defenses/config
@app.get("/api/defenses/config")
async def get_config():
    """获取当前防御配置 (简化版, 仅开关+参数)"""
    return {
        "code": 200,
        "message": "ok",
        "data": {
            "enabled_layers": _enabled_layers,
            "rule_count": _engine.rule_count,
            "enabled_rule_count": _engine.enabled_rule_count,
        },
    }


# 3. PUT /api/defenses/config
class UpdateConfigRequest(BaseModel):
    layer: str
    enabled: bool
    params: Optional[dict] = None


@app.put("/api/defenses/config")
async def update_config(req: UpdateConfigRequest):
    """更新某层的 enabled / params"""
    if req.layer not in _enabled_layers:
        raise HTTPException(404, f"Layer {req.layer} not found")
    _enabled_layers[req.layer] = req.enabled
    layer_enum = DefenseLayer(req.layer)
    _orchestrator.set_layer_enabled(layer_enum, req.enabled)
    return {
        "code": 200,
        "message": "ok",
        "data": {"layer": req.layer, "enabled": req.enabled},
    }


# 4. POST /api/defenses/rules
class AddRuleRequest(BaseModel):
    layer: str
    rule_id: Optional[str] = None
    name: str
    description: str = ""
    enabled: bool = True
    action: str = "log"
    priority: int = 99
    pattern_type: str = "regex"
    pattern: str = ""
    condition: Optional[str] = None
    target_fields: list[str] = Field(default_factory=lambda: ["content"])


@app.post("/api/defenses/rules")
async def add_rule(req: AddRuleRequest):
    """向指定层添加一条规则"""
    rule_id = req.rule_id or f"{_layer_prefix(DefenseLayer(req.layer))}{int(time.time()) % 100000}"
    rule = {
        "rule_id": rule_id,
        "name": req.name,
        "description": req.description,
        "enabled": req.enabled,
        "action": req.action,
        "priority": req.priority,
        "pattern_type": req.pattern_type,
        "pattern": req.pattern,
        "condition": req.condition,
        "target_fields": req.target_fields,
    }
    _engine.add_rule(rule)
    return {"code": 200, "message": "ok", "data": rule}


# 5. PUT /api/defenses/rules/{rule_id}
class UpdateRuleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    action: Optional[str] = None
    priority: Optional[int] = None
    pattern_type: Optional[str] = None
    pattern: Optional[str] = None
    condition: Optional[str] = None


@app.put("/api/defenses/rules/{rule_id}")
async def update_rule(rule_id: str, req: UpdateRuleRequest):
    """更新某条规则"""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    ok = _engine.update_rule(rule_id, updates)
    if not ok:
        raise HTTPException(404, f"Rule {rule_id} not found")
    return {"code": 200, "message": "ok", "data": _engine.get_rule(rule_id)}


# 6. DELETE /api/defenses/rules/{rule_id}
@app.delete("/api/defenses/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """删除某条规则"""
    ok = _engine.remove_rule(rule_id)
    if not ok:
        raise HTTPException(404, f"Rule {rule_id} not found")
    return {"code": 200, "message": "ok", "data": None}


# 7. POST /api/defenses/test
class DefenseTestRequest(BaseModel):
    content: str
    source: str
    enabled_layers: Optional[list[str]] = None
    content_type: str = "text"
    task_description: str = ""


@app.post("/api/defenses/test")
async def test_defense(req: DefenseTestRequest):
    """提交测试内容，返回逐层处理结果 — 通过完整 DefenseOrchestrator"""

    # 同步层启用状态 (用户可能通过 API 调整过)
    if req.enabled_layers:
        for layer in DefenseLayer:
            _orchestrator.set_layer_enabled(layer, layer.value in req.enabled_layers)

    ctx = DefenseContext(
        content=req.content,
        source=req.source,
        content_type=req.content_type,
        task_description=req.task_description,
        trust_level=1.0,
    )

    result = _orchestrator.run(ctx)

    # 恢复默认层启用状态
    if req.enabled_layers:
        _sync_orch_layers()

    return {
        "code": 200,
        "message": "ok",
        "data": {
            "passed": result.passed,
            "final_action": result.final_action,
            "layer_results": result.layer_results,
            "risk_score": result.risk_score,
            "processing_time_ms": result.processing_time_ms,
        },
    }


# 8. GET /api/defenses/stats
@app.get("/api/defenses/stats")
async def get_stats():
    """获取防御统计数据"""
    total_checks = sum(s.get("checks", 0) for s in _stats.values())
    total_blocked = sum(s.get("blocked", 0) for s in _stats.values())
    hit_stats = _engine.get_hit_stats()

    by_layer = {}
    for layer in DefenseLayer:
        s = _stats.get(layer.value, {"checks": 0, "blocked": 0})
        by_layer[layer.value] = {
            "checks": s.get("checks", 0),
            "blocked": s.get("blocked", 0),
            "rate": s["blocked"] / s["checks"] if s.get("checks", 0) > 0 else 0.0,
        }

    top_rules = [
        {"rule_id": rid, "hits": info["hits"],
         "rule_name": (_engine.get_rule(rid) or {}).get("name", "")}
        for rid, info in sorted(hit_stats.items(), key=lambda x: -x[1]["hits"])[:5]
    ]

    return {
        "code": 200,
        "message": "ok",
        "data": {
            "total_checks": total_checks,
            "total_blocked": total_blocked,
            "overall_block_rate": total_blocked / total_checks if total_checks > 0 else 0.0,
            "by_layer": by_layer,
            "top_rules": top_rules,
        },
    }


# 9. GET /api/defenses/strategies
@app.get("/api/defenses/strategies")
async def get_strategies():
    """获取预置的防御策略组合"""
    strategies = [
        {
            "name": "快速原型测试",
            "description": "仅启用核心交互和工具防护，适合开发阶段快速验证",
            "layers": {
                DefenseLayer.MODEL_INTERACTION.value: True,
                DefenseLayer.TOOL_CONSTRAINT.value: True,
            },
            "mode": "permissive",
        },
        {
            "name": "标准安全评估",
            "description": "源头+交互+工具+决策，适合常规评测场景",
            "layers": {
                DefenseLayer.SOURCE_GOVERNANCE.value: True,
                DefenseLayer.MODEL_INTERACTION.value: True,
                DefenseLayer.TOOL_CONSTRAINT.value: True,
                DefenseLayer.DECISION_SUPERVISION.value: True,
            },
            "mode": "balanced",
        },
        {
            "name": "全面深度防御",
            "description": "五层全开，最严格模式，适合金融/政务等高安全场景",
            "layers": {layer.value: True for layer in DefenseLayer},
            "mode": "strict",
        },
        {
            "name": "记忆投毒专项",
            "description": "强化记忆层 + 源头治理 + 决策监督",
            "layers": {
                DefenseLayer.SOURCE_GOVERNANCE.value: True,
                DefenseLayer.MEMORY_CONTROL.value: True,
                DefenseLayer.DECISION_SUPERVISION.value: True,
            },
            "mode": "balanced",
        },
        {
            "name": "RAG应用安全",
            "description": "强化源头治理和多源验证",
            "layers": {
                DefenseLayer.SOURCE_GOVERNANCE.value: True,
                DefenseLayer.MODEL_INTERACTION.value: True,
                DefenseLayer.DECISION_SUPERVISION.value: True,
            },
            "mode": "balanced",
        },
    ]
    return {"code": 200, "message": "ok", "data": {"strategies": strategies}}


# 10. PUT /api/defenses/strategies/{name}/apply
@app.put("/api/defenses/strategies/{name}/apply")
async def apply_strategy(name: str):
    """应用某个策略"""
    strategies_data = {
        "快速原型测试": {
            "source_governance": False,
            "model_interaction": True,
            "memory_control": False,
            "tool_constraint": True,
            "decision_supervision": False,
        },
        "标准安全评估": {
            "source_governance": True,
            "model_interaction": True,
            "memory_control": False,
            "tool_constraint": True,
            "decision_supervision": True,
        },
        "全面深度防御": {layer.value: True for layer in DefenseLayer},
        "记忆投毒专项": {
            "source_governance": True,
            "model_interaction": False,
            "memory_control": True,
            "tool_constraint": False,
            "decision_supervision": True,
        },
        "RAG应用安全": {
            "source_governance": True,
            "model_interaction": True,
            "memory_control": False,
            "tool_constraint": False,
            "decision_supervision": True,
        },
    }

    layer_config = strategies_data.get(name)
    if layer_config is None:
        raise HTTPException(404, f"Strategy {name} not found")

    for layer_name, enabled in layer_config.items():
        _enabled_layers[layer_name] = enabled

    return {
        "code": 200,
        "message": f"Strategy '{name}' applied",
        "data": {"enabled_layers": _enabled_layers},
    }


# ---- 健康检查 ----

@app.get("/health")
async def health():
    return {"status": "ok", "rule_count": _engine.rule_count}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
