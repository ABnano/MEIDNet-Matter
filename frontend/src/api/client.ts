import { STATIC_MIRROR, staticPath } from '@/lib/mirror';
import { sessionId } from '@/lib/session';

export class ApiError extends Error {
  status: number;
  code: string;
  fields: Array<{ loc: string; msg: string }>;
  retryAfter: number | null;
  constructor(status: number, code: string, message: string, fields: Array<{ loc: string; msg: string }> = [], retryAfter: number | null = null) {
    super(message);
    this.status = status; this.code = code; this.fields = fields; this.retryAfter = retryAfter;
  }
}

/** In the static mirror nothing is computed: a read is a file, anything else needs the live server. */
const LIVE_ONLY = 'This needs the live server: open MEIDNet Matter on Hugging Face (Babu09/MEIDNet-Matter).';

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (STATIC_MIRROR) {
    if ((init.method ?? 'GET').toUpperCase() !== 'GET') throw new ApiError(503, 'static_mirror', LIVE_ONLY);
    const res = await fetch(staticPath(path), { signal: init.signal });
    if (!res.ok) throw new ApiError(res.status, res.status === 404 ? 'static_mirror' : 'http_error', res.status === 404 ? LIVE_ONLY : `${res.status} ${res.statusText}`);
    return (await res.json()) as T;
  }
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  headers.set('X-Matter-Session', sessionId());
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const res = await fetch(path, { ...init, headers });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let body: unknown = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = null; }
  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string; fields?: Array<{ loc: string; msg: string }>; retry_after_s?: number } } | null)?.error;
    throw new ApiError(res.status, err?.code ?? 'http_error', err?.message ?? `${res.status} ${res.statusText}`, err?.fields ?? [], err?.retry_after_s ?? null);
  }
  return body as T;
}

/** A plain-text resource (a component's source): the body is returned as text, never parsed as JSON. */
export async function requestText(path: string, signal?: AbortSignal): Promise<string> {
  const headers = new Headers({ Accept: 'text/plain', 'X-Matter-Session': sessionId() });
  const res = STATIC_MIRROR ? await fetch(staticPath(path, 'raw'), { signal }) : await fetch(path, { headers, signal });
  const text = await res.text();
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try { message = (JSON.parse(text) as { error?: { message?: string } }).error?.message ?? message; } catch { /* not JSON */ }
    throw new ApiError(res.status, 'http_error', message);
  }
  return text;
}

export const get = <T,>(path: string, signal?: AbortSignal) => request<T>(path, { signal });
export const post = <T,>(path: string, body: unknown, signal?: AbortSignal) => request<T>(path, { method: 'POST', body: JSON.stringify(body), signal });
