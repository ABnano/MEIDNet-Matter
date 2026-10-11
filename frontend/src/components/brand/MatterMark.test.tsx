import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { MatterMark } from './MatterMark';

afterEach(cleanup);

describe('the Matter mark', () => {
  it('draws twice on one page (header and footer) without sharing an id, each reference finding its own definition', () => {
    const { container } = render(<><MatterMark /><MatterMark size={20} /></>);
    const marks = container.querySelectorAll('svg[role="img"][aria-label="MEIDNet Matter"]');
    expect(marks).toHaveLength(2);
    const ids = [...container.querySelectorAll('[id]')].map((e) => e.id);
    expect(ids.length).toBeGreaterThan(10);
    expect(new Set(ids).size).toBe(ids.length);
    for (const mark of marks) {
      const own = new Set([...mark.querySelectorAll('[id]')].map((e) => e.id));
      const refs = [...mark.innerHTML.matchAll(/url\(#([^)]+)\)/g)].map((m) => m[1]);
      expect(refs.length).toBeGreaterThan(10);
      for (const r of refs) expect(own.has(r)).toBe(true);
    }
  });
  it('ships the same drawing as the browser-tab icon, which also carries a simpler version for 16 px', () => {
    const icon = readFileSync('public/favicon.svg', 'utf8');
    expect(icon).toMatch(/viewBox="0 0 64 64"/);
    expect(icon).toMatch(/@media \(max-width:24px\)/);
    const ids = new Set([...icon.matchAll(/id="([^"]+)"/g)].map((m) => m[1]));
    for (const [, r] of icon.matchAll(/url\(#([^)]+)\)/g)) expect(ids.has(r)).toBe(true);
  });
});
