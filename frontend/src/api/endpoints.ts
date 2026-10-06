import { get, post } from './client';
import type { Candidate, CompareResult, Family, FamilySummary, Goal, GoalValidation, Health, Manifest, ModelInfo, Project, Readiness, Run, RunStatus, RunSummary, VersionInfo } from './types';

export const api = {
  health: () => get<Health>('/health'),
  version: () => get<VersionInfo>('/api/version'),
  project: (id: string, signal?: AbortSignal) => get<Project>(`/api/projects/${id}`, signal),
  dataset: (id: string) => get<Project['dataset']>(`/api/projects/${id}/dataset`),
  model: (id: string) => get<ModelInfo>(`/api/models/${id}`),
  families: () => get<FamilySummary[]>('/api/families'),
  family: (name: string, variant?: string | null) => get<Family>(`/api/families/${name}${variant ? `?variant=${encodeURIComponent(variant)}` : ''}`),
  validate: (goal: Goal, signal?: AbortSignal) => post<GoalValidation>('/api/goals/validate', goal, signal),
  readiness: (goal: Goal, signal?: AbortSignal) => post<Readiness>('/api/readiness', goal, signal),
  startRun: (goal: Goal, acknowledgeExploratory: boolean) => post<RunSummary>('/api/runs', { goal, acknowledge_exploratory: acknowledgeExploratory }),
  runs: () => get<RunSummary[]>('/api/runs'),
  runStatus: (id: string, signal?: AbortSignal) => get<RunStatus>(`/api/runs/${id}`, signal),
  run: (id: string, signal?: AbortSignal) => get<Run>(`/api/runs/${id}?view=full`, signal),
  stop: (id: string) => post<{ ok: boolean }>(`/api/runs/${id}/stop`, {}),
  candidates: (id: string) => get<Candidate[]>(`/api/runs/${id}/candidates`),
  candidate: (run: string, cid: string) => get<Candidate>(`/api/runs/${run}/candidates/${cid}`),
  compare: (run: string, ids: string[]) => post<CompareResult>(`/api/runs/${run}/compare`, { candidate_ids: ids }),
  manifest: (run: string) => get<Manifest>(`/api/runs/${run}/manifest`),
  urls: {
    cif: (run: string, cid: string) => `/api/runs/${run}/candidates/${cid}/cif`,
    record: (run: string, cid: string) => `/api/runs/${run}/candidates/${cid}/record.json`,
    csv: (run: string) => `/api/runs/${run}/export/candidates.csv`,
    json: (run: string) => `/api/runs/${run}/export/candidates.json`,
    bundle: (run: string) => `/api/runs/${run}/export/bundle.zip`,
    manifest: (run: string) => `/api/runs/${run}/manifest`,
  },
};
