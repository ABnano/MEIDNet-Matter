import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { HOME_TITLE, pageTitle } from './App';

describe('page titles', () => {
  it('names each page, so tabs and bookmarks say where they lead', () => {
    expect(pageTitle('/')).toBe(HOME_TITLE);
    expect(readFileSync('index.html', 'utf8')).toContain(`<title>${HOME_TITLE}</title>`);
    expect(pageTitle('/studies/mp20')).toBe('MP-20 study · MEIDNet Matter');
    expect(pageTitle('/pipeline/S6')).toBe('Block S6 · Pipeline · MEIDNet Matter');
    expect(pageTitle('/play/gen-abc')).toBe('Generation job · MEIDNet Matter');
    expect(pageTitle('/p/perov5-demo/runs/run-x1/c/run-x1-003')).toBe('Candidate · Perov-5 demo · MEIDNet Matter');
    expect(pageTitle('/p/perov5-demo/runs/run-x1')).toBe('Candidates · Perov-5 demo · MEIDNet Matter');
    expect(pageTitle('/nowhere')).toBe('MEIDNet Matter');
  });
});
