import type { Accepted } from '@/api/research';

/** How an accepted structure counts. Both models placing a cell inside the window is where the evidence starts, not where
 *  it ends: a structure whose own DFT value (in the training data or the reference set) contradicts both models is a
 *  failure of the check, and so is a new composition that is not charge balanced. Failures stay on the study page, as
 *  the record of how the check fails, and are left out of every count and of the strip on the home page. A known formula
 *  is not a failure on charge balance alone: the checker assumes common oxidation states (Na₂O₂ is a peroxide). */
export type AcceptedGroup = 'candidate' | 'rediscovered' | 'contradicted' | 'implausible';

export const groupOf = (a: Accepted): AcceptedGroup =>
  a.class.includes('contradicts') ? 'contradicted'
    : a.class.startsWith('rediscovered') || a.class.includes('confirms') ? 'rediscovered'
      : a.class.startsWith('new composition') && a.charge_balanced === false ? 'implausible'
        : 'candidate';

/** A study is split into groups only when it holds a failure; otherwise its accepted structures stay one table. */
export const hasFailures = (accepted: Accepted[]) => accepted.some((a) => { const g = groupOf(a); return g === 'contradicted' || g === 'implausible'; });
