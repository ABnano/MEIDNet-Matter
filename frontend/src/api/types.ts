// The JSON the backend returns (matter/api/*). Property ids (dir_gap, heat_all) are opaque strings.

export interface PropertyStats {
  label: string; unit: string; n: number; mean: number; std: number; min: number; max: number; median: number; span: number;
  percentiles: Record<string, number>; zero_share: number;
  histogram: { edges: number[]; counts: number[] };
  nonzero?: PropertyStats;
}

export interface FamilyCoverageGroup { allowed: string[]; present: string[]; absent: string[]; n_materials: Record<string, number> }

export interface DatasetSummary {
  dataset_id: string; title: string; source: { name: string; url: string };
  rows: { train: number; val: number; test: number; all: number };
  columns: string[]; properties: Record<string, PropertyStats>; properties_basis: string;
  elements: Record<string, number>;
  family_coverage: Record<string, Record<string, Record<string, FamilyCoverageGroup>>>;
  family_like_rows: Record<string, number>;
  profiles: Record<string, { n_materials: number; n_profiles: number; largest_group: number; share_with_10_or_more_pct: number }>;
  ambiguity_grid?: { columns: string[]; tolerance: number[]; axes: Record<string, number[]>; n_box: number[][]; n_formulas: number[][] };
}

export interface ModelProperty { column: string; label: string; unit: string; mean: number; std: number; min: number | null; max: number | null }

export interface ModelInfo {
  model_id: string; file: string; sha256: string; backend: string; legacy: boolean; trained_on: string; training_rows: number;
  properties: ModelProperty[]; max_sites: number; latent_dim: number; family: string | null;
  property_ranges: Record<string, [number, number]>; note: string; description: string;
  available: boolean; loaded: boolean; latents_available: boolean; caveats: string[];
  evaluation?: { split: string; n: number; space: string; property_prediction: Record<string, number>; representation: Record<string, number>;
    recoverability: Record<string, unknown> | null };
}

export interface Project {
  project_id: string; title: string; description: string; dataset_id: string; models: ModelInfo[]; default_model: string;
  default_goal: Goal; default_goal_summary: string; scope_statement: string;
  privacy: { hosted: string; local: string }; citations: Array<{ key: string; text: string; doi?: string; url?: string }>;
  dataset: DatasetSummary; limits: Record<string, number> | null; mode: 'public' | 'local';
}

export interface FamilyGroup {
  description: string; slots: number[]; multiplicity: number; elements: string[]; universe: string[];
  oxidation_states: Record<string, number[]>; coverage: { present: string[]; absent: string[]; n_materials: Record<string, number> };
}
export interface RuleEntry { id: string; rule: string; title: string; text: string; params: Record<string, unknown>; numeric: Record<string, number> }
export interface Family {
  name: string; title: string; description: string; variant: string | null; variants: Record<string, string>; n_sites: number;
  sites: Array<{ group: string; frac: [number, number, number] }>; lattice: { lattice: string; reference_a?: number } & Record<string, unknown>;
  lattice_rule: Record<string, unknown>; sampling_order: string[]; groups: Record<string, FamilyGroup>; constraints: RuleEntry[];
  presets: Record<string, { title: string; elements: string[]; text: string }>; n_elements: number;
}
export interface FamilySummary { name: string; title: string; description: string; variants: Record<string, string>; default_variant: string | null; n_sites: number; groups: string[] }

export type Kind = 'value' | 'values' | 'range' | 'at_least' | 'at_most' | 'maximize' | 'minimize';
export type Priority = 'primary' | 'secondary' | 'tertiary';
export interface Objective { property: string; kind: Kind; value?: number | null; values?: number[] | null; low?: number | null; high?: number | null; tolerance?: number | null; priority?: Priority; loss?: 'l1' | 'l2' | null }
export interface Goal {
  project_id?: string; model_id?: string | null; family: string; variant?: string | null; objectives: Objective[];
  elements?: { exclude: string[]; only: Record<string, string[]>; presets: string[] };
  max_elements?: number | null; rule_overrides?: Record<string, Record<string, number>>; disabled_rules?: string[];
  novelty?: { require_not_in_dataset: boolean };
  budget?: { per_target: number; population: number; rounds: number; steps: number; seed: number; min_cosine_sep: number };
  diverse_set?: boolean | null;
}

export interface FieldError { loc: string; msg: string }
export interface GoalValidation {
  ok: boolean; errors?: FieldError[]; message?: string; summary: string;
  generation?: Record<string, unknown> & { targets: Record<string, number>[] }; targets_explained?: string[]; windows?: Array<Record<string, unknown>>;
  notes?: string[]; estimated_seconds?: number; family?: { name: string; variant: string | null; n_sites: number; rules: string[] };
}

export type IndicatorStatus = 'ok' | 'caution' | 'not_ok' | 'info' | 'not_computed';
export type DomainStatus = 'in_distribution' | 'near_boundary' | 'extrapolating' | 'far_outside';
export interface Indicator {
  id: string; title: string; status: IndicatorStatus; sentences: string[]; measured: string; caveat: string | null;
  numbers: Record<string, unknown>; per_property?: Record<string, Record<string, unknown>> | null;
  // ambiguity
  word?: 'low' | 'moderate' | 'high'; one_to_many?: boolean; examples?: MaterialRow[]; search_advice?: SearchAdvice | null;
  // family support
  groups?: Record<string, { allowed: string[]; present: string[]; absent: string[]; excluded_by_user: string[]; coverage: number; n_materials: Record<string, number> }>;
  space?: { total: number; enumerated: number; sampled: boolean; rule_passing: number; rule_passing_fraction: number; in_dataset: number };
}
export interface SearchAdvice { diverse_set: boolean; per_target_min: number; min_cosine_sep_max: number }
export interface Readiness {
  verdict: 'SUPPORTED' | 'CAUTION' | 'NOT_RECOMMENDED'; exploratory_required: boolean; reasons: string[]; summary: string[];
  indicators: Record<'fidelity' | 'alignment' | 'recoverability' | 'target_support' | 'ambiguity' | 'family_support', Indicator>;
  model_id: string; caveats: string[]; goal_hash: string; search_advice: SearchAdvice | null; ambiguity: 'low' | 'moderate' | 'high';
  windows: Record<string, [number | null, number | null]>; notes: string[]; estimated_seconds: number; computed_in_ms: number;
}

export interface MaterialRow { material_id: string; split: string; formula: string; reduced_formula: string; site_key: string | null; properties: Record<string, number> }

export interface Progress { target: number; targets: number; round: number; rounds: number; step: number; steps: number; loss: number | null; seconds: number }
export type RunStatusName = 'queued' | 'running' | 'done' | 'stopped' | 'error' | 'interrupted';
export interface RunSummary {
  run_id: string; project_id: string; model_id: string; status: RunStatusName; mode: 'standard' | 'exploratory'; created: string;
  started: string | null; finished: string | null; error: string | null; summary: string; estimated_seconds: number;
  family: { name: string; variant: string | null; title: string }; progress: Progress; n_candidates: number; verdict: Readiness['verdict'] | null;
}
export interface RunStatus extends RunSummary { log: string[]; candidates: Candidate[]; notes: string[] }
export interface FunnelStage { id: string; title: string; lost: number; left: number; is_window: boolean }
export interface Funnel {
  target_index: number; target: Record<string, number>; rounds_used: number;
  latents: { proposed: number | null; decoded: number; passing: number; retained: number; skipped_duplicate: number; skipped_similar: number };
  attempts: { tried: number; chemistry_valid: number; target_compatible: number; stages: FunnelStage[] };
  rejections: { first_failure: Record<string, number>; failures_any: Record<string, number>; examples: Array<{ formula: string; first_failure: string; title: string; results: unknown }> };
}
export interface Run extends RunStatus {
  goal: Goal; generation: Record<string, unknown>; explained: string[];
  readiness: Pick<Readiness, 'verdict' | 'exploratory_required' | 'reasons' | 'goal_hash' | 'caveats' | 'search_advice' | 'windows' | 'ambiguity' | 'summary'>;
  funnel: Funnel[] | null; timings: Record<string, number>; manifest: Manifest | null;
}

export interface CandidateProperty {
  label: string; unit: string; objective: Kind | null; target: number | null; predicted: number; difference: number | null;
  uncertainty: number | null; uncertainty_note: string; training_range: [number, number];
  domain: { status: DomainStatus; word: string; reason: string }; in_window: boolean | null; window: [number | null, number | null] | null;
  evidence_label: string; dft_value?: number | null; dft_label?: string;
}
export interface CandidateRule { id: string; rule: string; title: string; text: string; passed: boolean; value: number | null; window: [number | null, number | null] | null; detail: string; evidence_label: string }
export interface NearestMaterial extends MaterialRow { cosine: number; encoder_prediction: Record<string, number>; evidence_label: string }
export interface NoveltyCheck { checked_against: string; found: boolean; match: (MaterialRow & { matched_by: string; n_matches: number }) | null; label: string }
export interface Candidate {
  candidate_id: string; run_id: string; index: number; target_index: number; round: number;
  identity: { formula: string; reduced_formula: string; site_key: string | null; elements: Record<string, string>; family: string; variant: string | null; backend: string; model_id: string };
  structure: { file: string; lattice_a: number; n_sites: number; chemiscope: { size: number; names: string[]; x: number[]; y: number[]; z: number[]; cell: number[] };
    sites: Array<{ element: string; frac: [number, number, number] }>; lattice: number[][] };
  properties: Record<string, CandidateProperty>; domain: { status: DomainStatus; word: string };
  constraints: CandidateRule[]; rules_passed: number; rules_total: number;
  model_evidence: {
    encoder_prediction: Record<string, number>;
    agreement: Record<string, { decoder: number; encoder: number; difference: number; in_std: number | null; word: string; label: string }>;
    latent_norm: number | null; latent_hit_clip: boolean; score: number | null; nearest_training: NearestMaterial[]; latent_distance: number | null;
    local_density: { n_within: number; fraction: number; windows: Record<string, [number, number]> }; latent: number[];
  };
  novelty: { method: string; dataset: NoveltyCheck; training_split: NoveltyCheck };
  stability: { status: string; stages: string[]; records: unknown[] };
  flags: string[]; mode: 'standard' | 'exploratory'; why: string; engine: Record<string, unknown>; enrichment_error?: string;
}
export interface Manifest { manifest_version: number; run_id: string; status: string; mode: string; software: Record<string, string | null>; dataset: Record<string, unknown>; model: Record<string, unknown>; design: Record<string, unknown>; candidates: Array<{ candidate_id: string; formula: string; file: string; sha256: string | null }>; exported_files: Record<string, string>; durations_s: Record<string, number>; [k: string]: unknown }
export interface CompareResult { candidates: Candidate[]; pairwise_cosine: number[][]; properties: Record<string, { label: string; unit: string }> }
export interface Health { status: string; version: string; meidnet_version: string; mode: string; model_loaded: boolean }
export interface VersionInfo { matter: string; meidnet: string; git_sha: string; mode: string; space_id: string | null; [k: string]: unknown }
