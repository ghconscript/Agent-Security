// 实验编排 API
import type {
  Experiment, ExperimentTimelineEvent,
} from './types';
import { mockExperiments, mockTimelineEvents } from './mock';
import { AttackFamily, DefenseLayer, ExperimentStatus } from '../utils/constants';

export async function getExperiments(): Promise<Experiment[]> {
  await delay();
  return [...mockExperiments].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
}

export async function getExperiment(runId: string): Promise<Experiment | undefined> {
  await delay();
  return mockExperiments.find((e) => e.run_id === runId);
}

export async function createExperiment(data: {
  name: string;
  target_ids: string[];
  attack_families: AttackFamily[];
  defense_layers: DefenseLayer[];
  description?: string;
}): Promise<Experiment> {
  await delay();
  const exp: Experiment = {
    run_id: `RUN_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}_${String(mockExperiments.length + 1).padStart(3, '0')}`,
    name: data.name,
    target_ids: data.target_ids,
    attack_families: data.attack_families,
    defense_layers: data.defense_layers,
    description: data.description,
    status: ExperimentStatus.DRAFT,
    created_at: new Date().toISOString(),
  };
  mockExperiments.push(exp);
  return exp;
}

export async function startExperiment(runId: string): Promise<Experiment> {
  await delay();
  const exp = mockExperiments.find((e) => e.run_id === runId);
  if (!exp) throw new Error('实验不存在');
  exp.status = ExperimentStatus.RUNNING;
  exp.started_at = new Date().toISOString();
  exp.progress = { total_samples: exp.max_rounds || 50, completed: 0, failed: 0, percentage: 0 };
  return exp;
}

export async function stopExperiment(runId: string): Promise<Experiment> {
  await delay();
  const exp = mockExperiments.find((e) => e.run_id === runId);
  if (!exp) throw new Error('实验不存在');
  exp.status = ExperimentStatus.STOPPED;
  exp.finished_at = new Date().toISOString();
  return exp;
}

export async function getTimeline(_runId: string): Promise<ExperimentTimelineEvent[]> {
  await delay();
  return mockTimelineEvents;
}

function delay(ms = 300): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
