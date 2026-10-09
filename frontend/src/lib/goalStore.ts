import type { Goal } from '@/api/types';

const key = (projectId: string) => `matter_goal:${projectId}`;

/** The goal being edited, kept per tab so the goal, readiness and search pages share it. A stored goal that names a model
 *  the project no longer has (a tab open across a release) falls back to the project's default model. */
export function loadGoal(projectId: string, fallback: Goal, modelIds?: string[]): Goal {
  try {
    const raw = sessionStorage.getItem(key(projectId));
    if (raw) {
      const goal = JSON.parse(raw) as Goal;
      return modelIds && goal.model_id && !modelIds.includes(goal.model_id) ? { ...goal, model_id: fallback.model_id ?? null } : goal;
    }
  } catch { /* storage blocked or corrupt */ }
  return fallback;
}

const RUN_GOALS = 'matter_run_goals';

/** The goal of each search started or opened in this browser (the last 50), so a link to an expired search can restore it. */
export function rememberRunGoal(runId: string, goal: Goal) {
  try {
    const all = JSON.parse(localStorage.getItem(RUN_GOALS) || '{}') as Record<string, Goal>;
    delete all[runId];
    all[runId] = goal;
    const ids = Object.keys(all);
    for (const id of ids.slice(0, Math.max(0, ids.length - 50))) delete all[id];
    localStorage.setItem(RUN_GOALS, JSON.stringify(all));
  } catch { /* storage blocked */ }
}

export function goalOfRun(runId: string): Goal | null {
  try { return (JSON.parse(localStorage.getItem(RUN_GOALS) || '{}') as Record<string, Goal>)[runId] ?? null; } catch { return null; }
}

export function saveGoal(projectId: string, goal: Goal) {
  try { sessionStorage.setItem(key(projectId), JSON.stringify(goal)); } catch { /* storage blocked */ }
}

export function clearGoal(projectId: string) {
  try { sessionStorage.removeItem(key(projectId)); } catch { /* storage blocked */ }
}
