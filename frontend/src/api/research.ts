// The research routes (pipeline blocks, studies, checkpoints, generation jobs) and their types.
import { apiUrl } from '@/lib/mirror';
import { get, post, requestText } from './client';

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
  /** What S0 decided for each dataset: generation, screening or candidate sets (shown in place of S0's grade). */
  dataset_routes?: Record<string, string>;
}
export interface ComponentInfo { file: string; bytes: number; sha256: string; blocks: string[]; runnable: string; needs: string[] }

export interface StudyIndexEntry { id: string; title: string; dataset: string; mode: string; headline: string; order: number }
export interface Verdict { grade: Grade; note: string }
export interface Rediscovery { formula: string; label_gap: number; judge_gap: number; e_hull: number; literature: string; spacegroup?: number | null }
export interface Accepted {
  requested: number; formula: string; label_structure_gap: number; judge_gap: number; amd_nearest: number | null; known_formula: boolean;
  recorded_gaps: number[]; class: string; charge_balanced: boolean | null; relaxation_drop_eV_atom: number | null;
  spacegroup_designed: number | null; spacegroup_relaxed: number | null; natoms: number; file: string; flag: string;
  /** The relaxed cell as sites and lattice (0.4.0), for the 3D cards. */
  structure?: { sites: Array<{ element: string; frac: [number, number, number] }>; lattice: number[][] } | null;
  /** A study with several routes (0.7.0): the route that accepted it, its energy above the hull (one potential for every
   *  phase) with the reason when the value is not a stability statement, the reference entry of a known compound. */
  route?: string; e_hull?: number | null; e_hull_note?: string; reference_id?: string | null;
  /** The study it belongs to, when cards from several studies are shown together. */
  study?: string;
}
export interface StudyRoute {
  id: string; title: string; how: string; funnel: Array<[string, number]>; classes: Record<string, number>;
  collapsed: Array<{ formula: string; target: number; contact_ratio: number }>; stable_share: number | null; not_assessed: number;
}
export interface StudyStability {
  potential: string; reference: string; n: number; mae_eV: number; median_abs_error_eV: number; agreement: number; spearman: number | null;
  outliers: string[]; mae_without_outliers: number | null; spearman_without_outliers: number | null; agreement_without_outliers: number | null;
}
export interface Calibration {
  window_eV: number; metal_floor_eV: number;
  /** relaxed = the relaxed cells that stayed physical and bulk-like; collapsed_on_relaxation (0.6.0) = those whose atoms were pushed into each
   *  other; not_bulk_on_relaxation (0.8.0) = slabs and sparse cells. */
  funnel: { generated: number; both_judges: number; collapsed_on_relaxation?: number; not_bulk_on_relaxation?: number; relaxed: number; final: number };
  collapsed_on_relaxation?: Array<{ formula: string; target: number; contact_ratio: number }>;
  /** 0.8.0: relaxed cells that are a slab or a sparse cell (an empty layer over 6 Å, a packing fraction under 0.12). */
  not_bulk_on_relaxation?: Array<{ formula: string; target: number; reason: string }>;
  judge: { fidelity: number; n: number; mae: number; spearman: number; mae_on_nonzero: number | null; share_zero_truth: number };
  per_target: Array<{ requested: number; generated: number; both_judges: number; relaxed: number; final: number; generated_judge_mean: number;
    delivered_mean: number | null; delivered_sd: number | null; delivered_min: number | null; delivered_max: number | null; bias: number | null;
    drop_median: number | null; spacegroup_kept: number | null; final_formulas: string[] }>;
  accuracy: { mae_generated_cells: number; mae_relaxed_cells: number; mae_relaxed_ci95: [number, number]; within_window: number; of: number;
    /** 0.8.0: the judge's error on the same cells before relaxation, so that before and after compare like with like. */
    mae_same_cells_before_relaxation?: number | null; same_cells?: number };
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
  pool?: { generated: number; both_judges_generated: number; relaxed: number; accepted: number; collapsed_on_relaxation?: number; not_bulk_on_relaxation?: number };
  checks?: Array<{ stage: string; check: string; status: string; detail: string }>;
  lessons?: string[];
  /** A study with several routes to its candidates (0.7.0). */
  routes?: StudyRoute[]; stability?: StudyStability; cross_checks?: string[]; window_eV?: number;
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
  /** 0.8.0: closest atoms over the sum of their radii, the thickest empty layer and the packing fraction of the generated cell. */
  geometry?: { contact_ratio: number; empty_layer_A: number; packing: number } | null;
  evidence: Record<string, string>; stability: { status: string; note: string };
  /** 0.4.0: the cell for the 3D card and the three statuses, kept apart. */
  lattice_matrix?: number[][]; sites?: Array<{ element: string; frac: [number, number, number] }>;
  statuses?: { gap_window: 'both models' | 'label only' | 'judge only' | 'neither'; charge_balance: 'yes' | 'no' | 'unknown'; relaxed: string };
}
export interface CellSites { sites: Array<{ element: string; frac: [number, number, number] }>; lattice: number[][] }
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
  component: (file: string, signal?: AbortSignal) => requestText(`/api/pipeline/components/${encodeURIComponent(file)}`, signal),
  componentUrl: (file: string) => apiUrl(`/api/pipeline/components/${encodeURIComponent(file)}`),
  studies: (signal?: AbortSignal) => get<{ studies: StudyIndexEntry[] }>('/api/studies', signal),
  study: (id: string, signal?: AbortSignal) => get<Study>(`/api/studies/${id}`, signal),
  studyFileUrl: (id: string, name: string) => apiUrl(`/api/studies/${id}/files/${name}`),
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
