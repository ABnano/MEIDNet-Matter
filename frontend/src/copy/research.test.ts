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
  it('the Generate page describes the filter it applies: kept by its own label, judged afterwards', () => {
    expect(research.play.lead).toMatch(/keeps the cells whose label falls inside your window/);
    expect(research.play.lead).not.toMatch(/returns the ones both place inside your window/);
  });
  it('the Generate page links its family pointer once, without repeating the sentence', () => {
    const { familyPointer, familyLink } = research.play;
    const parts = familyPointer.split(familyLink);
    expect(parts).toHaveLength(2);                     // the link text occurs exactly once
    expect(parts[0] + familyLink + parts[1]).toBe(familyPointer);
    expect(parts[1]).not.toMatch(/Method ›/);           // the text after the link does not repeat it
  });
});
