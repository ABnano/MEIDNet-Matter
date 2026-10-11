import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { Study } from '@/api/research';
import { datasets, home } from '@/copy/research';
import { groupOf, hasFailures } from './accepted';

const study = (id: string) => JSON.parse(readFileSync(`../examples/research/studies/${id}/study.json`, 'utf8')) as Study;

describe('how an accepted structure counts', () => {
  it('splits the double perovskites into candidates awaiting DFT, a compound found again and the failures', () => {
    const acc = study('jarvis-dp').accepted!;
    const of = (g: string) => acc.filter((a) => groupOf(a) === g).map((a) => a.formula).sort();
    expect(of('candidate')).toEqual(['Cs2InFeBr6', 'K2LiScI6', 'Rb2KInCl6', 'Rb2LiFeBr6', 'Rb2NaFeBr6', 'Tl2InSbF6', 'Tl2InSbI6']);
    expect(of('rediscovered')).toEqual(['Ba2MgWO6']);
    expect(of('contradicted')).toEqual(['Rb2InSbCl6', 'Rb2InSbI6', 'SbTeO3']);
    expect(of('implausible')).toEqual(['Tl2Br']);                     // a new composition that is not charge balanced
    expect(hasFailures(acc)).toBe(true);
    expect(acc.find((a) => a.formula === 'Rb2KInCl6')!.flag).toMatch(/Materials Project/);   // new here, not unknown
  });
  it('leaves the MP-20 study whole: a known formula is not a failure on charge balance alone', () => {
    const acc = study('mp20').accepted!;
    expect(hasFailures(acc)).toBe(false);
    expect(groupOf(acc.find((a) => a.formula === 'Na2O2')!)).toBe('candidate');   // a peroxide the checker cannot balance
  });
  it('puts the judge error next to the window of a study without a calibration', () => {
    const dp = study('jarvis-dp');
    expect(dp.judge_mae_eV).toBe(0.82);
    expect(dp.judge_mae_eV!).toBeGreaterThan(dp.window_eV!);
  });
});

describe('which data each stage runs on', () => {
  it('names both datasets under the hero, and the Generate card names its own model', () => {
    expect(home.scope).toMatch(/Perov-5/);
    expect(home.scope).toMatch(/MP-20/);
    expect(home.stages.find((s) => s[1] === 'Generate')![3]).toMatch(/separate model trained on MP-20/);
  });
  it('states the split the studies use, and the 1,419 of the Perov-5 runs next to it', () => {
    expect(datasets.perov5.join(' ')).toMatch(/11,356 training, 3,787 validation and 3,785 test/);
    expect(study('perov5').dataset.split_note).toMatch(/1,419 materials, against 3,787/);
    expect(study('user-246').dataset.uploaded).toMatch(/246 entries; 236 matched/);
  });
});
