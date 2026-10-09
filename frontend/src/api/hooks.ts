import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './endpoints';
import { ApiError, isGone } from './client';
import type { RunStatus } from './types';

const cache = new Map<string, unknown>();

/** A cached read: the same key is fetched once per page lifetime; `invalidate(prefix)` clears it. */
export function useResource<T>(key: string | null, fetcher: (signal: AbortSignal) => Promise<T>) {
  const [state, setState] = useState<{ data: T | null; error: ApiError | Error | null; loading: boolean }>(() => ({
    data: key && cache.has(key) ? (cache.get(key) as T) : null, error: null, loading: !!key && !cache.has(key),
  }));
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!key) return;
    if (cache.has(key)) { setState({ data: cache.get(key) as T, error: null, loading: false }); return; }
    const ctrl = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    fetcher(ctrl.signal).then((data) => { cache.set(key, data); setState({ data, error: null, loading: false }); })
      .catch((error: Error) => { if (error.name !== 'AbortError') setState({ data: null, error, loading: false }); });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tick]);
  const reload = useCallback(() => { if (key) cache.delete(key); setTick((t) => t + 1); }, [key]);
  return { ...state, reload };
}

export function invalidate(prefix: string) {
  for (const k of [...cache.keys()]) if (k.startsWith(prefix)) cache.delete(k);
}

/** Polls a run until it finishes: 1 s for the first 30 s, then 2 s, then 3 s; backs off on failures; pauses when hidden. */
export function useRunPolling(runId: string | null) {
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [failures, setFailures] = useState(0);
  const timer = useRef<number | null>(null);
  const startedAt = useRef(Date.now());
  const [resumeTick, setResumeTick] = useState(0);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    const ctrl = new AbortController();
    startedAt.current = Date.now();
    let consecutive = 0;
    const schedule = (ms: number) => { timer.current = window.setTimeout(poll, ms); };
    const delay = () => { const age = Date.now() - startedAt.current; return age < 30_000 ? 1000 : age < 120_000 ? 2000 : 3000; };
    async function poll() {
      if (cancelled) return;
      if (document.visibilityState === 'hidden') { schedule(2000); return; }
      try {
        const s = await api.runStatus(runId!, ctrl.signal);
        if (cancelled) return;
        consecutive = 0; setFailures(0); setError(null); setStatus(s);
        if (s.status === 'queued' || s.status === 'running') schedule(delay());
      } catch (e) {
        if (cancelled || (e as Error).name === 'AbortError') return;
        if (isGone(e)) { setError(e); return; }                     // expired or unknown: no retry can bring it back
        consecutive += 1; setFailures(consecutive);
        if (consecutive >= 6) { setError(e as Error); return; }
        schedule(Math.min(15_000, 1000 * 2 ** consecutive));
      }
    }
    const onVisible = () => { if (document.visibilityState === 'visible' && timer.current) { clearTimeout(timer.current); poll(); } };
    document.addEventListener('visibilitychange', onVisible);
    poll();
    return () => { cancelled = true; ctrl.abort(); if (timer.current) clearTimeout(timer.current); document.removeEventListener('visibilitychange', onVisible); };
  }, [runId, resumeTick]);

  const retry = useCallback(() => { setError(null); setFailures(0); setResumeTick((t) => t + 1); }, []);
  return { status, error, failures, retry };
}
