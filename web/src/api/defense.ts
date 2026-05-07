// 防御模块 API
// Phase 2: 扩展至 10 条端点, 与 defense_engine/server.py 对齐

import type {
  DefenseLayerConfig, DefenseRule,
  DefenseTestRequest, DefenseTestResult,
  DefenseStats, DefenseStrategy,
} from './types';
import {
  mockDefenseLayers, mockDefenseTestResult,
  mockDefenseStats, mockDefenseStrategies,
} from './mock';
import { DefenseLayer, DefenseMode } from '../utils/constants';

// ---- 层配置 (已有, 更新返回值) ----

export async function getDefenseLayers(): Promise<DefenseLayerConfig[]> {
  await delay();
  return mockDefenseLayers.map(l => ({ ...l }));
}

export async function getDefenseConfig(): Promise<{ enabled_layers: Record<string, boolean>; rule_count: number; enabled_rule_count: number }> {
  await delay();
  return {
    enabled_layers: Object.fromEntries(mockDefenseLayers.map(l => [l.layer, l.enabled]) as [string, boolean][]),
    rule_count: mockDefenseLayers.flatMap(l => l.rules).length,
    enabled_rule_count: mockDefenseLayers.flatMap(l => l.rules).filter(r => r.enabled).length,
  };
}

export async function updateDefenseConfig(data: {
  layer: DefenseLayer;
  enabled: boolean;
  params?: Record<string, unknown>;
}): Promise<{ layer: string; enabled: boolean }> {
  await delay();
  const layer = mockDefenseLayers.find((l) => l.layer === data.layer);
  if (!layer) throw new Error(`Layer ${data.layer} not found`);
  layer.enabled = data.enabled;
  if (data.params) layer.params = { ...layer.params, ...data.params };
  return { layer: data.layer, enabled: data.enabled };
}

// ---- 规则 CRUD (扩展) ----

export async function getDefenseRules(layer?: DefenseLayer): Promise<DefenseRule[]> {
  await delay();
  if (layer) {
    const l = mockDefenseLayers.find((l) => l.layer === layer);
    return l ? [...l.rules] : [];
  }
  return mockDefenseLayers.flatMap((l) => l.rules);
}

export async function addDefenseRule(
  layer: DefenseLayer,
  rule: Partial<DefenseRule> & { name: string },
): Promise<DefenseRule> {
  await delay();
  const l = mockDefenseLayers.find((l) => l.layer === layer);
  if (!l) throw new Error(`Layer ${layer} not found`);
  const prefix = { source_governance: 'SG', model_interaction: 'MI', memory_control: 'MC', tool_constraint: 'TC', decision_supervision: 'DS' }[layer];
  const newRule: DefenseRule = {
    rule_id: `${prefix}${Date.now().toString(36).toUpperCase()}`,
    name: rule.name,
    description: rule.description || '',
    enabled: rule.enabled ?? true,
    action: rule.action || 'log',
    priority: rule.priority || 99,
    pattern_type: rule.pattern_type || 'regex',
    pattern: rule.pattern || '',
    condition: rule.condition ?? undefined,
    target_fields: rule.target_fields || ['content'],
    hit_count: 0,
    version: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  l.rules.push(newRule);
  return newRule;
}

export async function updateDefenseRule(ruleId: string, updates: Partial<DefenseRule>): Promise<DefenseRule> {
  await delay();
  for (const layer of mockDefenseLayers) {
    const rule = layer.rules.find(r => r.rule_id === ruleId);
    if (rule) {
      Object.assign(rule, updates, { updated_at: new Date().toISOString(), version: (rule.version || 1) + 1 });
      return rule;
    }
  }
  throw new Error(`Rule ${ruleId} not found`);
}

export async function deleteDefenseRule(ruleId: string): Promise<void> {
  await delay();
  for (const layer of mockDefenseLayers) {
    const idx = layer.rules.findIndex(r => r.rule_id === ruleId);
    if (idx !== -1) {
      layer.rules.splice(idx, 1);
      return;
    }
  }
  throw new Error(`Rule ${ruleId} not found`);
}

// ---- 防御测试 (新增) ----

export async function testDefense(req: DefenseTestRequest): Promise<DefenseTestResult> {
  await delay(500); // 模拟后端处理时间
  return { ...mockDefenseTestResult };
}

// ---- 统计 (新增) ----

export async function getDefenseStats(): Promise<DefenseStats> {
  await delay();
  return { ...mockDefenseStats };
}

// ---- 策略 (新增) ----

export async function getDefenseStrategies(): Promise<DefenseStrategy[]> {
  await delay();
  return [...mockDefenseStrategies];
}

export async function applyDefenseStrategy(name: string): Promise<{ enabled_layers: Record<string, boolean> }> {
  await delay();
  const strategy = mockDefenseStrategies.find(s => s.name === name);
  if (!strategy) throw new Error(`Strategy ${name} not found`);
  for (const [layerName, enabled] of Object.entries(strategy.layers)) {
    const layer = mockDefenseLayers.find(l => l.layer === layerName);
    if (layer) layer.enabled = enabled;
  }
  return {
    enabled_layers: Object.fromEntries(mockDefenseLayers.map(l => [l.layer, l.enabled])),
  };
}

function delay(ms = 300): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
