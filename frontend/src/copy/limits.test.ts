import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { Study } from '@/api/research';
import { limits, STUDY_EVIDENCE } from './limits';
import { STUDY_DATASETS, play } from './research';

const study = (id: string) => JSON.parse(readFileSync(`../examples/research/studies/${id}/study.json`, 'utf8')) as Study;
const text = JSON.stringify(limits) + JSON.stringify(STUDY_EVIDENCE);

describe('the scope-and-limits statement', () => {
  it('has a row for every study, and keeps the site\'s vocabulary', () => {
    for (const [id] of STUDY_DATASETS) expect(STUDY_EVIDENCE[id], id).toBeDefined();
    expect(text).not.toMatch(/\bhonest/i);
    expect(text).not.toMatch(/small model/i);
  });
  it('states the upload\'s split and size as its study records them', () => {
    const ds = study('user-246').dataset as Record<string, number | string>;
    expect([ds.train, ds.val, ds.test, ds.rows]).toEqual([166, 36, 34, 236]);
    expect(limits.small).toMatch(/246 entries \(236 matched; 166 for training, 36 for validation, 34 for testing\)/);
    expect(STUDY_EVIDENCE['user-246'].data).toBe('236 matched of 246 uploaded (166 / 36 / 34)');
  });
  it('quotes the densities and judge errors of the studies', () => {
    const cpe = (id: string) => Number(study(id).dataset.compositions_per_element);
    expect(cpe('user-246').toFixed(1)).toBe('11.3');
    expect(cpe('jarvis-dp').toFixed(1)).toBe('48.5');
    expect(cpe('mp-perovskites')).toBe(12);
    expect(cpe('mp20')).toBe(817);
    expect(text).toMatch(/48\.5 per element\), MP perovskites \(12\), the upload \(11\.3\)/);
    expect(study('mp20').calibration!.judge.mae.toFixed(2)).toBe('0.10');
    expect(study('jarvis-dp').judge_mae_eV).toBe(0.82);
    expect(text).toMatch(/0\.10 eV on MP-20, 0\.82 eV on the double perovskites/);
  });
  it('says the generation threshold is provisional, and why', () => {
    expect(limits.thresholdNote).toMatch(/218.*rows per cation element.*549/);
    expect(limits.open[0]).toMatch(/re-measured/);
  });
  it('matches the studies\' own limits where both speak', () => {
    expect(study('mp20').limits.join(' ')).toMatch(/1\.2–17 eV\/atom \(median 5\.4\) and moved atoms by up to 0\.4–9\.7 Å/);
    expect(study('jarvis-dp').verdicts.S1.note).toMatch(/^Metal \/ non-metal accuracy 0\.823 share \(not met\)/);
    expect(study('perov5').headline).toMatch(/lanthanide absent from the training data/);
  });
  it('the Generate page links Scope and limits once', () => {
    const tail = play.familyPointer.split(play.familyLink)[1];
    expect(tail.split(play.limitsLink)).toHaveLength(2);
  });
});
