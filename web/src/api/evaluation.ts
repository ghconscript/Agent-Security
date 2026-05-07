// 评估结果 API
import type {
  EvaluationSummary, EvaluationTrendPoint, FamilyEvaluation,
  EvaluationCompare,
} from './types';
import { mockEvaluationSummaries, mockTrendData } from './mock';

const defaultSummary = mockEvaluationSummaries['RUN_20260428_001'];

export async function getEvaluationSummary(runId: string): Promise<EvaluationSummary> {
  await delay();
  return mockEvaluationSummaries[runId] || { ...defaultSummary, run_id: runId };
}

export async function getEvaluationMetrics(runId: string): Promise<{
  byFamily: Record<string, FamilyEvaluation>;
  task_drift_rate: number;
  refusal_rate: number;
  fpr: number;
  fnr: number;
}> {
  await delay();
  const s = mockEvaluationSummaries[runId] || defaultSummary;
  return {
    byFamily: s.by_family,
    task_drift_rate: s.task_drift_rate,
    refusal_rate: s.refusal_rate,
    fpr: s.fpr,
    fnr: s.fnr,
  };
}

export async function getTrend(_runId: string): Promise<EvaluationTrendPoint[]> {
  await delay();
  return [...mockTrendData];
}

export async function compareEvaluations(runIds: string[]): Promise<EvaluationCompare> {
  await delay();
  const metrics: Record<string, EvaluationSummary> = {};
  for (const id of runIds) {
    metrics[id] = mockEvaluationSummaries[id] || { ...defaultSummary, run_id: id };
  }
  return { run_ids: runIds, metrics };
}

function delay(ms = 300): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
