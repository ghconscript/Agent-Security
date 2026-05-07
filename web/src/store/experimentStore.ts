import { create } from 'zustand';
import type { Experiment } from '../api/types';
import * as experimentApi from '../api/experiment';
import { AttackFamily, DefenseLayer } from '../utils/constants';

interface ExperimentState {
  experiments: Experiment[];
  currentExperiment: Experiment | null;
  loading: boolean;

  fetchExperiments: () => Promise<void>;
  getExperiment: (runId: string) => Promise<void>;
  createExperiment: (data: {
    name: string;
    target_ids: string[];
    attack_families: AttackFamily[];
    defense_layers: DefenseLayer[];
    description?: string;
  }) => Promise<Experiment>;
  startExperiment: (runId: string) => Promise<void>;
  stopExperiment: (runId: string) => Promise<void>;
}

export const useExperimentStore = create<ExperimentState>((set) => ({
  experiments: [],
  currentExperiment: null,
  loading: false,

  fetchExperiments: async () => {
    set({ loading: true });
    const experiments = await experimentApi.getExperiments();
    set({ experiments, loading: false });
  },

  getExperiment: async (runId) => {
    const exp = await experimentApi.getExperiment(runId);
    set({ currentExperiment: exp || null });
  },

  createExperiment: async (data) => {
    const exp = await experimentApi.createExperiment(data);
    set((s) => ({ experiments: [exp, ...s.experiments] }));
    return exp;
  },

  startExperiment: async (runId) => {
    const exp = await experimentApi.startExperiment(runId);
    set((s) => ({
      experiments: s.experiments.map((e) => (e.run_id === runId ? exp : e)),
      currentExperiment: exp,
    }));
  },

  stopExperiment: async (runId) => {
    const exp = await experimentApi.stopExperiment(runId);
    set((s) => ({
      experiments: s.experiments.map((e) => (e.run_id === runId ? exp : e)),
      currentExperiment: exp,
    }));
  },
}));
