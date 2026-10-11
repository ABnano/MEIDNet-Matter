import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it } from 'vitest';
import { DatasetPrimer } from './DatasetPrimer';

afterEach(cleanup);

describe('the datasets in plain words', () => {
  it('opens where the home page links, with where to browse each dataset and where it comes from', () => {
    render(<MemoryRouter><DatasetPrimer /></MemoryRouter>);
    expect(document.getElementById('perov5')).not.toBeNull();         // "What is Perov-5?" lands here
    expect(document.getElementById('mp20')).not.toBeNull();
    expect(screen.getByRole('link', { name: 'Browse it in Explore →' })).toHaveAttribute('href', '/explore');
    expect(screen.getByRole('link', { name: 'The Perov-5 case study →' })).toHaveAttribute('href', '/studies/perov5');
    const sources = screen.getAllByRole('link', { name: /The split files \(CDVAE\)/ }).map((a) => a.getAttribute('href'));
    expect(sources).toEqual(['https://github.com/txie-93/cdvae/tree/main/data/perov_5', 'https://github.com/txie-93/cdvae/tree/main/data/mp_20']);
    expect(screen.getByRole('link', { name: /The original database \(CMR, DTU\)/ })).toHaveAttribute('href', 'https://cmr.fysik.dtu.dk/cubic_perovskites/cubic_perovskites.html');
  });
});
