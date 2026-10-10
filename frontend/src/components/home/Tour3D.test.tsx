import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router';
import { afterEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { Tour3D } from './Tour3D';
import { Crystal3D } from './Crystal3D';

afterEach(cleanup);

function Where() { return <div data-testid="where">{useLocation().pathname}</div>; }

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
  it('follows the page the player points its link at, inside the app', () => {
    render(<MemoryRouter initialEntries={['/']}><Tour3D /><Where /></MemoryRouter>);
    const link = screen.getByRole('link', { name: 'Start exploring →' });
    link.setAttribute('href', '/train');               // what the player does while the Model chapter is on screen
    fireEvent.click(link);
    expect(screen.getByTestId('where')).toHaveTextContent('/train');
  });
  it('ships the two scripts it loads, and the copied tour points at this app, not at the Studio', () => {
    const tour = readFileSync('public/tour/prism-tour.js', 'utf8');
    expect(readFileSync('public/tour/prism3d.js', 'utf8')).toMatch(/window\.Prism3D/);
    expect(tour).toMatch(/getElementById\("tour3d"\)/);
    expect(tour).not.toMatch(/\/studio\//);                          // every "open" link leads to a page of this app
    for (const path of ['/explore', '/train', '/generate', '/studies']) expect(tour).toContain(`"${path}"`);
    // mounted on each new section the home page renders, and stopped when the page is left
    expect(tour).toMatch(/window\.PrismTour = \{mount: mount\}/);
    expect(tour).toMatch(/destroy: function/);
  });
});

describe('the crystal of MEIDNet Prism', () => {
  it('renders a described canvas with its caption', () => {
    render(<Crystal3D />);
    expect(screen.getByRole('img', { name: /cubic ABX3 perovskite/ })).toBeInTheDocument();
    expect(screen.getByText(/drag to rotate/)).toBeInTheDocument();
  });
  it('ships the scene as a function the page mounts on each canvas, without the lettering of the Prism headline', () => {
    const hero = readFileSync('public/tour/prism-hero.js', 'utf8');
    expect(hero).toMatch(/window\.PrismHero = \{mount: mount\}/);
    expect(hero).toMatch(/destroy: function/);
    expect(hero).not.toMatch(/data-mol/);
  });
});
