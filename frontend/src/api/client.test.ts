import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, request, requestText } from './client';

const response = (body: string, init: { status?: number; type?: string } = {}) =>
  new Response(body, { status: init.status ?? 200, headers: { 'Content-Type': init.type ?? 'application/json' } });

afterEach(() => { vi.unstubAllGlobals(); });

describe('the API client', () => {
  it('returns a plain-text body as text, which the JSON path cannot', async () => {
    const source = '"""A component."""\nimport os\n';
    vi.stubGlobal('fetch', vi.fn(async () => response(source, { type: 'text/plain; charset=utf-8' })));
    await expect(requestText('/api/pipeline/components/x.py')).resolves.toBe(source);
    await expect(request<string>('/api/pipeline/components/x.py')).resolves.toBeNull();   // the defect 0.4.2 fixed
  });
  it('turns an error envelope into an ApiError for text requests too', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(JSON.stringify({ error: { code: 'not_found', message: "no component named 'y.py'" } }), { status: 404 })));
    await expect(requestText('/api/pipeline/components/y.py')).rejects.toMatchObject({ status: 404, message: "no component named 'y.py'" } satisfies Partial<ApiError>);
  });
});
