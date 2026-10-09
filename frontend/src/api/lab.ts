// Explore and Train Lite: the two stages added in 0.10.0, and their types.
import { apiUrl } from '@/lib/mirror';
import { get, post } from './client';

/** One training material on the latent map (explore.json's columns: material_id, formula, x, y, the properties, site_key). */
export interface ExplorePoint { material_id: string; formula: string; x: number; y: number; heat_all: number; dir_gap: number; site_key: string }
export interface ExplorePayload {
  schema: string; project_id: string; model_id: string; split: string; columns: string[]; points: Array<[string, string, number, number, number, number, string]>;
  projection: { method: string; explained_variance: [number, number]; note: string }; n: number;
}
export interface Cell { lattice: number[][]; sites: Array<{ element: string; frac: [number, number, number] }> }
export interface Neighbour { material_id: string; formula: string; split: string; cosine: number; properties: Record<string, number>; encoder_prediction: Record<string, number> }
export interface MaterialDetail {
  material_id: string; split: string; formula: string; reduced_formula: string; site_key: string | null; properties: Record<string, number>;
  cell: Cell | null; neighbours: Neighbour[]; encoder_prediction: Record<string, number> | null; note: string;
}

export interface TrainOptions {
  available: boolean; epochs?: number[]; seconds_per_epoch_estimate?: number; limits?: { epochs: number; seconds: number };
  subset?: { train: number; val: number; seed: number; nonzero_gap_train: number; nonzero_gap_val: number; sampling: string; spread: Record<string, number>; spread_dir_gap_nonzero: number };
  full_model?: { model_id: string; training_rows: number | null; epochs: number | null; val_mae: Record<string, number>; val_mae_dir_gap_nonzero: number; val_r2: Record<string, number> };
  recipe?: string;
}
export interface EpochPoint { epoch: number; loss: number; parts: Record<string, number>; alignment_cosine: number; val_mae: Record<string, number>; retrieval_top1: number }
export interface TrainResult {
  n_val: number; epochs_run: number; stopped_early: boolean; seconds: number;
  val: { mae: Record<string, number>; r2: Record<string, number>; mae_dir_gap_nonzero: number; retrieval_top1: number };
  against_spread: Record<string, { mae: number; spread: number; ratio: number | null; basis: string; full_model_mae: number }>;
  full_model: TrainOptions['full_model'];
  predictions: { columns: string[]; rows: Array<[string, string, number, number, number, number]> };
  map: { explained_variance: [number, number]; points: Array<[string, number, number, number]> };
  what_this_is: string; full_training_command: string;
}
export interface TrainJob {
  job_id: string; status: 'queued' | 'running' | 'done' | 'stopped' | 'error' | 'interrupted'; created: string; started: string | null; finished: string | null;
  error: string | null; request: { epochs: number; seed: number }; limits: Record<string, number> | null; estimated_seconds: number;
  progress: { epoch: number; epochs: number; phase: string; seconds: number };
  history?: EpochPoint[]; log?: string[]; subset?: TrainOptions['subset']; result?: TrainResult | null; provenance?: Record<string, string | null> | null;
}

export const lab = {
  explore: (project: string, signal?: AbortSignal) => get<ExplorePayload>(`/api/explore/${project}`, signal),
  material: (project: string, id: string, signal?: AbortSignal) => get<MaterialDetail>(`/api/explore/${project}/materials/${encodeURIComponent(id)}`, signal),
  trainOptions: (signal?: AbortSignal) => get<TrainOptions>('/api/train/options', signal),
  train: (epochs: number, seed: number) => post<TrainJob>('/api/train', { epochs, seed }),
  trainings: () => get<TrainJob[]>('/api/train'),
  training: (id: string, signal?: AbortSignal) => get<TrainJob>(`/api/train/${id}`, signal),
  stopTraining: (id: string) => post<{ ok: boolean }>(`/api/train/${id}/stop`, {}),
  modelUrl: (id: string) => apiUrl(`/api/train/${id}/model.pt`),
  configUrl: (id: string) => apiUrl(`/api/train/${id}/config.yaml`),
  predictionsUrl: (id: string) => apiUrl(`/api/train/${id}/predictions.csv`),
};

export const pointsOf = (p: ExplorePayload): ExplorePoint[] =>
  p.points.map(([material_id, formula, x, y, heat_all, dir_gap, site_key]) => ({ material_id, formula, x, y, heat_all, dir_gap, site_key }));
