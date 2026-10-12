import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

// the research menu beside the page loads the study index; the page itself is static
vi.mock('@/api/research', () => ({ research: { studies: () => Promise.resolve({ studies: [] }) } }));

import Limits from './Limits';

afterEach(cleanup);

describe('the Scope and limits page', () => {
  it('has the five sections the study pages link to, and points to the DFT validation of the paper', () => {
    render(<MemoryRouter initialEntries={['/limits']}><Limits /></MemoryRouter>);
    for (const id of ['evidence', 'data', 'studies', 'structures', 'strengths']) expect(document.getElementById(id), id).not.toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: 'Scope and limits' })).toBeInTheDocument();
  });
  it('lists all five studies, each linked to its page', () => {
    render(<MemoryRouter><Limits /></MemoryRouter>);
    const table = document.getElementById('studies')!;
    for (const id of ['perov5', 'mp-perovskites', 'user-246', 'mp20', 'jarvis-dp']) {
      expect(within(table).getAllByRole('link').some((a) => a.getAttribute('href') === `/studies/${id}`), id).toBe(true);
    }
  });
  it('tells a newcomer with their own data where to start', () => {
    render(<MemoryRouter><Limits /></MemoryRouter>);
    expect(screen.getByRole('link', { name: 'How to start →' })).toHaveAttribute('href', '/start-with-my-data');
    expect(screen.getByTestId('small-data')).toHaveTextContent(/Small datasets support property prediction, not generation/);
  });
});
