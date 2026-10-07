import { describe, expect, it } from 'vitest';
import * as research from './research';
import * as landing from './landing';

function strings(obj: unknown, out: string[] = []): string[] {
  if (typeof obj === 'string') out.push(obj);
  else if (Array.isArray(obj)) obj.forEach((x) => strings(x, out));
  else if (obj && typeof obj === 'object') Object.values(obj).forEach((x) => strings(x, out));
  return out;
}

describe('site copy', () => {
  const all = [...strings(research), ...strings(landing)];
  it('has prose', () => { expect(all.length).toBeGreaterThan(20); });
  it('never uses the word the site rules exclude', () => {
    for (const s of all) expect(s).not.toMatch(/\bhonest/i);
  });
  it('does not compare paper numbers against reruns', () => {
    for (const s of all) expect(s).not.toMatch(/paper (reports|reported|claims)/i);
  });
});
