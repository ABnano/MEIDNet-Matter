import { describe, expect, it } from 'vitest';
import { GRADE_WORD, verdictWord } from './index';

describe('verdict words', () => {
  it('reads a grade as a measurement against a band, never as a bare FAIL', () => {
    expect(verdictWord('PASS')).toBe('Meets');
    expect(verdictWord('WARN')).toBe('Borderline');
    expect(verdictWord('FAIL')).toBe('Not met');
    expect(verdictWord('INFO')).toBe('Context');
    expect(verdictWord('PARTIAL')).toBe('Partly met');
    expect(verdictWord('—')).toBe('—');
    expect(Object.values(GRADE_WORD).join(' ')).not.toMatch(/FAIL|PASS|WARN/);
  });
  it('shows S0 as the route the data supports', () => {
    expect(verdictWord('FAIL', 'screening')).toBe('Screening');
    expect(verdictWord('FAIL', 'candidate sets')).toBe('Candidate sets');
    expect(verdictWord('PASS', 'generation')).toBe('Generation');
  });
});
