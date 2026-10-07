// The research routes (pipeline blocks, studies, checkpoints, generation jobs) and their types.
import { get, post, request } from './client';

export type Grade = 'PASS' | 'WARN' | 'FAIL' | 'INFO' | 'PARTIAL';

export interface MetricDef {
  id: string; name: string; definition: string; unit: string; better: 'higher' | 'lower'; pass_at: number | null; warn_at: number | null;
  band: { pass: string; warn: string; fail: string }; meaning_good: string; meaning_bad: string; remedy: string; computed_by: string;
  info_only: boolean; conditional_on: [string, string, number] | null; cap: string; superseded_by: string; recalibrated: string;
  dataset_agnostic: boolean; new_dataset_note: string; reference: Record<string, number>; reference_grades: Record<string, Grade>; reference_note: string;
}
export interface ComponentRef { file: string; note: string; viewable: boolean; runnable: 'web' | 'local' | 'hpc'; needs: string[] }
export interface BlockDef {
  id: string; name: string; question: string; purpose: string; when: string; verdict_rule: string; caveats: string[]; metrics: MetricDef[];
  components: ComponentRef[];
}
export interface BlocksPayload {
  schema: string; grades: Grade[]; configs: Record<string, { label?: string; known?: string }>; blocks: BlockDef[];
  dataset_history: Array<{ dataset: string; description: string; items: Array<{ blocks: string; text: string }> }>;
  validation_table: Record<string, Record<string, Grade>>; dataset_verdicts: Record<string, Record<string, Grade>>;
}
export interface ComponentInfo { file: string; bytes: number; sha256: string; blocks: string[]; runnable: string; needs: string[] }

export interface StudyIndexEntry { id: string; title: string; dataset: string; mode: string; headline: string; order: number }
export interface Verdict { grade: Grade; note: string }
export interface Rediscovery { formula: string; label_gap: number; judge_gap: number; e_hull: number; literature: string; spacegroup?: number | null }
export interface Accepted {
  requested: number; formula: string; label_structure_gap: number; judge_gap: number; amd_nearest: number | null; known_formula: boolean;
  recorded_gaps: number[]; class: string; charge_balanced: boolean | null; relaxation_drop_eV_atom: number | null;
  spacegroup_designed: number | null; spacegroup_relaxed: number | null; natoms: number; file: string; flag: string;
}
export interface Calibration {
  window_eV: number; metal_floor_eV: number; funnel: { generated: number; both_judges: number; relaxed: number; final: number };
  judge: { fidelity: number; n: number; mae: number; spearman: number; mae_on_nonzero: number | null; share_zero_truth: number };
  per_target: Array<{ requested: number; generated: number; both_judges: number; relaxed: number; final: number; generated_judge_mean: number;
    delivered_mean: number | null; delivered_sd: number | null; delivered_min: number | null; delivered_max: number | null; bias: number | null;
    drop_median: number | null; spacegroup_kept: number | null; final_formulas: string[] }>;
  accuracy: { mae_generated_cells: number; mae_relaxed_cells: number; mae_relaxed_ci95: [number, number]; within_window: number; of: number };
  linearity: { slope: number; intercept: number; r2: number; spearman: number; ideal: string };
  precision: { within_target_sd_median: number | null };
  resolution: Array<{ pair: [number, number]; delta_mean: number; pooled_sd: number; separable: boolean }>;
  range: { requested: number[]; served: number[] };
  novelty: { amd_median: number; amd_min: number; novel_share: number; unique_share: number } | null;
  stability_note: string;
}
export interface Study {
  schema: string; id: string; title: string; order: number; mode: string; headline: string;
  dataset: Record<string, unknown> & { name: string };
  verdicts: Record<string, Verdict>;
  target_following: Record<string, unknown>;
  checkpoints: string[]; reproduce: Array<{ step: string; command: string }>; limits: string[];
  files: Record<string, { bytes: number; sha256: string; media: string }>; sources: string[];
  ablation?: { columns: string[]; rows: Array<Record<string, unknown>>; note: string };
  rediscoveries?: Rediscovery[]; judges?: Record<string, Record<string, unknown>>;
  calibration?: Calibration; accepted?: Accepted[]; accepted_classes?: Record<string, number>;
  pool?: { generated: number; both_judges_generated: number; relaxed: number; accepted: number };
  checks?: Array<{ stage: string; check: string; status: string; detail: string }>;
  lessons?: string[];
}

export interface CheckpointInfo {
  id: string; file?: string; config?: string | null; sha256: string | null; bytes: number | null; dataset: string; study: string; role: string;
  ship: boolean; loadable: boolean; description: string; urls?: string[]; properties?: string[]; max_sites?: number; geometry?: string;
  epochs?: number; seed?: number; element_features?: string; available: boolean; loaded: boolean; download_url: string | null; config_text?: string;
  files?: Array<{ file: string; sha256: string | null; bytes: number | null; urls: string[] }>; needs?: string;
}

export interface GenerateRequest {
  model_id: string; property?: 'band_gap'; targets: number[]; per_target: number; window_eV: number; require_anion: boolean;
  exclude_elements: string[]; seed: number; oversample?: number;
}
export interface GenCandidate {
  candidate_id: string; target_eV: number; formula: string; natoms: number; n_orbits: number; spacegroup: number;
  label_structure_eV: number | null; label_formation_energy_eV_atom: number | null; judge_eV: number | null;
  within_window: { label: boolean; judge: boolean }; metal_by_judge: boolean | null; consensus: boolean; charge_balanced: boolean | null;
  known_formula: boolean | null; recorded_gaps_eV: number[]; amd_nearest_reference: number | null; novel_by_amd: boolean | null;
  lattice: { a: number; b: number; c: number; alpha: number; beta: number; gamma: number }; volume_per_atom: number; file: string; sha256: string;
  evidence: Record<string, string>; stability: { status: string; note: string };
}
export interface GenJob {
  job_id: string; status: 'queued' | 'running' | 'done' | 'stopped' | 'error' | 'interrupted'; created: string; started: string | null;
  finished: string | null; error: string | null; request: GenerateRequest; notes: string[]; limits: Record<string, number> | null;
  estimated_seconds: number; progress: { target_index: number; targets: number; attempts: number; kept: number; phase: string; seconds: number };
  n_candidates: number; n_consensus: number; log?: string[]; candidates?: GenCandidate[];
  funnel?: { attempted: number; kept: number; judged: number; consensus: number } | null;
  per_target?: Array<{ requested: number; kept: number; consensus: number; label_mean_eV: number | null; judge_mean_eV: number | null }> | null;
  judge?: { name: string; weights: string; fidelity: number; available: boolean; error: string | null; qualification: Record<string, number | string | null> | null };
  model?: CheckpointInfo; relax_command?: string;
}

export const research = {
  blocks: (signal?: AbortSignal) => get<BlocksPayload>('/api/pipeline/blocks', signal),
  block: (id: string, signal?: AbortSignal) => get<BlockDef>(`/api/pipeline/blocks/${id}`, signal),
  components: () => get<ComponentInfo[]>('/api/pipeline/components'),
  component: (file: string, signal?: AbortSignal) => request<string>(`/api/pipeline/components/${encodeURIComponent(file)}`, { signal, headers: { Accept: 'text/plain' } }),
  componentUrl: (file: string) => `/api/pipeline/components/${encodeURIComponent(file)}`,
  studies: (signal?: AbortSignal) => get<{ studies: StudyIndexEntry[] }>('/api/studies', signal),
  study: (id: string, signal?: AbortSignal) => get<Study>(`/api/studies/${id}`, signal),
  studyFileUrl: (id: string, name: string) => `/api/studies/${id}/files/${name}`,
  checkpoints: (signal?: AbortSignal) => get<{ release: string; checkpoints: CheckpointInfo[] }>('/api/checkpoints', signal),
  checkpoint: (id: string) => get<CheckpointInfo>(`/api/checkpoints/${id}`),
  generate: (body: GenerateRequest) => post<GenJob>('/api/generate', body),
  jobs: () => get<GenJob[]>('/api/generate'),
  job: (id: string, signal?: AbortSignal) => get<GenJob>(`/api/generate/${id}`, signal),
  jobFull: (id: string, signal?: AbortSignal) => get<GenJob>(`/api/generate/${id}?view=full`, signal),
  stopJob: (id: string) => post<{ ok: boolean }>(`/api/generate/${id}/stop`, {}),
  cifUrl: (job: string, cid: string) => `/api/generate/${job}/candidates/${cid}/cif`,
  zipUrl: (job: string) => `/api/generate/${job}/export/cifs.zip`,
};
