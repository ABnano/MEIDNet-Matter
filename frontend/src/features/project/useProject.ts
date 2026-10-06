import { api } from '@/api/endpoints';
import { useResource } from '@/api/hooks';

export function useProject(projectId: string) {
  return useResource(`project:${projectId}`, (signal) => api.project(projectId, signal));
}

export function useFamily(name: string | null, variant: string | null | undefined) {
  return useResource(name ? `family:${name}:${variant ?? ''}` : null, () => api.family(name!, variant));
}
