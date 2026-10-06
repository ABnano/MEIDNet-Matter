import type { Goal } from '@/api/types';

const key = (projectId: string) => `matter_goal:${projectId}`;

/** The goal being edited, kept per tab so the goal, readiness and search pages share it. */
export function loadGoal(projectId: string, fallback: Goal): Goal {
  try {
    const raw = sessionStorage.getItem(key(projectId));
    if (raw) return JSON.parse(raw) as Goal;
  } catch { /* storage blocked or corrupt */ }
  return fallback;
}

export function saveGoal(projectId: string, goal: Goal) {
  try { sessionStorage.setItem(key(projectId), JSON.stringify(goal)); } catch { /* storage blocked */ }
}

export function clearGoal(projectId: string) {
  try { sessionStorage.removeItem(key(projectId)); } catch { /* storage blocked */ }
}
