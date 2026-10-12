import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { limits } from '@/copy/limits';
import { FlowDiagram, RouteDiagram } from './Diagrams';

afterEach(cleanup);

describe('the diagrams of the reading pages', () => {
  it('draw a workflow as an ordered list of numbered, coloured steps', () => {
    render(<FlowDiagram testId="f" caption="A workflow" steps={[
      { title: 'Target', sub: 'a', color: 'var(--c-targets)' }, { title: 'Decode', sub: 'b', color: 'var(--c-model)' }]} />);
    const steps = within(screen.getByTestId('f')).getAllByRole('listitem');
    expect(steps.map((s) => s.querySelector('b')?.textContent)).toEqual(['Target', 'Decode']);
    expect(steps[0]).toHaveTextContent('01');
    expect(steps[1].style.getPropertyValue('--k')).toBe('var(--c-model)');
    expect(screen.getByText('A workflow').tagName).toBe('FIGCAPTION');
  });
  it('show the data gate with its three routes and the check they share', () => {
    render(<RouteDiagram {...limits.route} testId="r" />);
    const fig = screen.getByTestId('r');
    for (const t of ['Your dataset', 'Data gate (block S0), before training', 'Generation without a family', 'Screening within a family', 'Candidate sets', 'The same check on every route']) {
      expect(within(fig).getByText(t)).toBeInTheDocument();
    }
  });
});
