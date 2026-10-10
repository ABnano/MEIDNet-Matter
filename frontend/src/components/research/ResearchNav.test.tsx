import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/research', () => ({
  research: {
    studies: () => Promise.resolve({
      studies: [
        { id: 'mp20', title: 'MP-20', dataset: 'MP-20', mode: 'generation', headline: '', order: 4 },
        { id: 'perov5', title: 'Perov-5', dataset: 'Perov-5', mode: 'generation', headline: '', order: 1 },
      ],
    }),
  },
}));

import { ResearchLayout } from './ResearchNav';

const at = (path: string) =>
  render(<MemoryRouter initialEntries={[path]}><ResearchLayout><h1>The page</h1></ResearchLayout></MemoryRouter>);
const menu = () => screen.getByRole('navigation', { name: 'Research' });
const linkNames = () => within(menu()).getAllByRole('link').map((a) => a.textContent);

afterEach(cleanup);   // this project's vitest runs without globals, so Testing Library does not clean up by itself

describe('research menu', () => {
  it('names the four sections, marks the page being read, and keeps the page in the main region', async () => {
    at('/method');
    expect(linkNames()).toEqual(expect.arrayContaining(['Overview', 'Case studies', 'Evaluation pipeline', 'Methodology']));
    expect(within(menu()).getByRole('link', { name: 'Methodology' })).toHaveAttribute('aria-current', 'page');
    expect(within(menu()).getByRole('link', { name: 'Overview' })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('main')).toHaveTextContent('The page');
    expect(within(menu()).queryByRole('link', { name: 'Perov-5' })).toBeNull();   // the studies open only in their section
    expect(within(menu()).queryByRole('link', { name: /^S\d/ })).toBeNull();      // and so do the blocks
  });

  it('opens the case studies, in their reading order, on a study page', async () => {
    at('/studies/mp20');
    await within(menu()).findByRole('link', { name: 'Perov-5' });
    const names = linkNames();
    expect(names.indexOf('Perov-5')).toBeLessThan(names.indexOf('MP-20'));
    expect(within(menu()).getByRole('link', { name: 'MP-20' })).toHaveAttribute('aria-current', 'page');
    expect(within(menu()).getByRole('link', { name: 'Case studies' })).not.toHaveAttribute('aria-current');
  });

  it('lists the ten blocks inside the evaluation pipeline', () => {
    at('/pipeline/S6');
    const blocks = within(menu()).getAllByRole('link', { name: /^S\d/ });
    expect(blocks).toHaveLength(10);
    expect(within(menu()).getByRole('link', { name: /^S6/ })).toHaveAttribute('aria-current', 'page');
  });
});
