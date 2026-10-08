import { describe, expect, it } from 'vitest';
import { apiUrl, STATIC_MIRROR, staticPath } from './mirror';

describe('the static mirror', () => {
  it('maps a read to the file scripts/build_mirror.py writes, relative to the page', () => {
    expect(staticPath('/api/studies/mp20')).toBe('static-api/api/studies/mp20.json');
    expect(staticPath('/api/pipeline/blocks')).toBe('static-api/api/pipeline/blocks.json');
    expect(staticPath('/api/generate/abc?view=full')).toBe('static-api/api/generate/abc@view=full.json');
    expect(staticPath('/health')).toBe('static-api/health.json');
  });
  it('keeps a raw file under its own name', () => {
    expect(staticPath('/api/studies/mp20/files/accepted/Sr(HgCl)2_T2_n20_295.cif', 'raw')).toBe('static-api/api/studies/mp20/files/accepted/Sr(HgCl)2_T2_n20_295.cif');
    expect(staticPath('/api/pipeline/components/hull_mlip.py', 'raw')).toBe('static-api/api/pipeline/components/hull_mlip.py');
  });
  it('leaves links alone outside the mirror build', () => {
    expect(STATIC_MIRROR).toBe(false);                                     // vitest runs in mode "test"
    expect(apiUrl('/api/studies/mp20/files/pool_candidates.csv')).toBe('/api/studies/mp20/files/pool_candidates.csv');
  });
});
