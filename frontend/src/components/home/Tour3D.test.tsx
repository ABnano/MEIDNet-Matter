import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { Tour3D } from './Tour3D';

afterEach(cleanup);

describe('the animated tour', () => {
  it('renders the markup the player script looks for, with its controls named for a screen reader', () => {
    render(<MemoryRouter><Tour3D /></MemoryRouter>);
    const root = document.getElementById('tour3d');
    expect(root).not.toBeNull();
    expect(root!.querySelector('canvas')).not.toBeNull();
    expect(root!.querySelector('.t3-strip')).not.toBeNull();
    expect(screen.getByRole('button', { name: 'Play the tour' })).toBeInTheDocument();
    expect(screen.getByRole('slider', { name: /Position in the tour/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Start exploring →' })).toHaveAttribute('href', '/explore');
  });
  it('ships the two scripts it loads, and the copied tour points at this app, not at the Studio', () => {
    const tour = readFileSync('public/tour/prism-tour.js', 'utf8');
    expect(readFileSync('public/tour/prism3d.js', 'utf8')).toMatch(/window\.Prism3D/);
    expect(tour).toMatch(/getElementById\("tour3d"\)/);
    expect(tour).not.toMatch(/\/studio\//);                          // every "open" link leads to a page of this app
    for (const path of ['/explore', '/train', '/generate', '/studies']) expect(tour).toContain(`"${path}"`);
  });
});
